"""Immutable puzzle catalog loading, validation, and answer-safe projection."""

from __future__ import annotations

import contextlib
import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import (
    Classification,
    Color,
    DomainError,
    Scope,
    board_from_fen,
    classify,
    normalize_squares,
    reconstruct,
    resolve_scope,
    union_classifications,
)

SCHEMA_VERSION = 2
RULES_VERSION = "1.0.0"
CATALOG_SIZE = 100

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
PACKAGE_KINDS = ("curated", "user")
RESERVED_SLUGS = frozenset({"bookmarked"})


class CatalogError(RuntimeError):
    """The shipped catalog is absent, corrupt, or incompatible."""


@dataclass(frozen=True, slots=True)
class Puzzle:
    puzzle_id: str
    source_url: str
    source_fen: str
    first_move_uci: str
    presented_fen: str
    side_to_move: Color
    rating: int | None
    themes: tuple[str, ...]
    answers: dict[Color, Classification]
    solution_moves_uci: tuple[str, ...]
    opening: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "puzzle_id": self.puzzle_id,
            "source_url": self.source_url,
            "presented_fen": self.presented_fen,
            "side_to_move": self.side_to_move.value,
            "rating": self.rating,
            "themes": list(self.themes),
            "opening": self.opening,
        }


def canonical_payload(data: dict[str, Any]) -> bytes:
    cleaned = {key: value for key, value in data.items() if key != "catalog_checksum"}
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":")).encode()


def checksum(data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(data)).hexdigest()


def _parse_puzzle(raw: dict[str, Any]) -> Puzzle:
    try:
        side = Color(raw["side_to_move"])
        answers = {
            color: Classification(
                normalize_squares(raw["answers_by_color"][color.value]["undefended"]),
                normalize_squares(raw["answers_by_color"][color.value]["hanging"]),
            )
            for color in Color
        }
        opening_raw = raw.get("opening")
        puzzle = Puzzle(
            puzzle_id=str(raw["puzzle_id"]),
            source_url=str(raw["source_url"]),
            source_fen=str(raw["source_fen"]),
            first_move_uci=str(raw["first_move_uci"]),
            presented_fen=str(raw["presented_fen"]),
            side_to_move=side,
            rating=int(raw["rating"]) if raw.get("rating") is not None else None,
            themes=tuple(str(theme) for theme in raw["themes"]),
            answers=answers,
            solution_moves_uci=tuple(str(move) for move in raw["solution_moves_uci"]),
            opening=str(opening_raw) if opening_raw else None,
        )
    except (KeyError, TypeError, ValueError, DomainError) as exc:
        raise CatalogError("invalid puzzle record") from exc
    board = board_from_fen(puzzle.presented_fen)
    if Color.from_chess(board.turn) is not puzzle.side_to_move:
        raise CatalogError(f"side-to-move mismatch for {puzzle.puzzle_id}")
    if puzzle.first_move_uci:
        try:
            reconstructed = reconstruct(puzzle.source_fen, puzzle.first_move_uci)
        except DomainError as exc:
            raise CatalogError(f"source reconstruction failed for {puzzle.puzzle_id}") from exc
        if reconstructed.fen != puzzle.presented_fen:
            raise CatalogError(f"presented FEN mismatch for {puzzle.puzzle_id}")
    elif puzzle.source_fen and puzzle.source_fen != puzzle.presented_fen:
        raise CatalogError(
            f"source FEN must equal presented FEN when no first move: {puzzle.puzzle_id}"
        )
    return puzzle


def _parse_package_block(raw: dict[str, Any] | None, *, fallback_slug: str) -> dict[str, Any]:
    """Validate and normalise the optional `package` block. Missing → curated default."""
    if raw is None:
        return {
            "slug": fallback_slug,
            "title": fallback_slug,
            "description": "",
            "kind": "curated",
            "created_at": None,
            "query": None,
        }
    if not isinstance(raw, dict):
        raise CatalogError("package block must be an object")
    slug = str(raw.get("slug", "")).strip()
    if not SLUG_RE.match(slug):
        raise CatalogError(f"invalid package slug: {slug!r}")
    if slug in RESERVED_SLUGS:
        raise CatalogError(f"package slug is reserved: {slug!r}")
    kind = raw.get("kind", "curated")
    if kind not in PACKAGE_KINDS:
        raise CatalogError(f"invalid package kind: {kind!r}")
    return {
        "slug": slug,
        "title": str(raw.get("title") or slug),
        "description": str(raw.get("description") or ""),
        "kind": kind,
        "created_at": raw.get("created_at"),
        "query": raw.get("query"),
    }


class PuzzleCatalog:
    def __init__(
        self,
        data: dict[str, Any],
        *,
        verify_answers: bool = True,
        require_hanging: bool = True,
        source_path: Path | None = None,
    ) -> None:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise CatalogError("unsupported catalog schema version")
        if data.get("rules_version") != RULES_VERSION:
            raise CatalogError("unsupported rules version")
        if data.get("catalog_checksum") != checksum(data):
            raise CatalogError("catalog checksum mismatch")
        target_count = int(data.get("target_count", CATALOG_SIZE))
        if target_count <= 0 or target_count % 5 != 0:
            raise CatalogError("target_count must be a positive multiple of 5")
        raw_puzzles = data.get("puzzles")
        if not isinstance(raw_puzzles, list) or len(raw_puzzles) != target_count:
            raise CatalogError(f"catalog must contain exactly {target_count} puzzles")
        puzzles = [_parse_puzzle(raw) for raw in raw_puzzles]
        if len({puzzle.puzzle_id for puzzle in puzzles}) != len(puzzles):
            raise CatalogError("duplicate puzzle ID")
        if len({puzzle.presented_fen for puzzle in puzzles}) != len(puzzles):
            raise CatalogError("duplicate presented position")
        if verify_answers:
            for puzzle in puzzles:
                for color in Color:
                    if classify(puzzle.presented_fen, color) != puzzle.answers[color]:
                        raise CatalogError(f"answer mismatch for {puzzle.puzzle_id}")
                if require_hanging and not puzzle.answers[puzzle.side_to_move].hanging:
                    raise CatalogError(f"side to move has no hanging piece: {puzzle.puzzle_id}")
        fallback_slug = source_path.stem if source_path is not None else "default"
        self.package = _parse_package_block(data.get("package"), fallback_slug=fallback_slug)
        self.target_count = target_count
        self.metadata = {key: value for key, value in data.items() if key != "puzzles"}
        self._puzzles = {puzzle.puzzle_id: puzzle for puzzle in puzzles}
        self._ids = tuple(self._puzzles)
        self.source_path = source_path

    @property
    def slug(self) -> str:
        return self.package["slug"]

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        verify_answers: bool = True,
        require_hanging: bool = True,
    ) -> PuzzleCatalog:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"unable to read catalog: {path}") from exc
        return cls(
            data,
            verify_answers=verify_answers,
            require_hanging=require_hanging,
            source_path=path,
        )

    def get(self, puzzle_id: str) -> Puzzle:
        try:
            return self._puzzles[puzzle_id]
        except KeyError as exc:
            raise CatalogError("unknown puzzle") from exc

    def next(
        self, previous_id: str | None = None, *, chooser: random.Random | None = None
    ) -> Puzzle:
        ids = [puzzle_id for puzzle_id in self._ids if puzzle_id != previous_id]
        if not ids:
            ids = list(self._ids)
        return self._puzzles[(chooser or random.SystemRandom()).choice(ids)]

    def expected(self, puzzle_id: str, scope: Scope) -> Classification:
        puzzle = self.get(puzzle_id)
        return union_classifications(puzzle.answers, resolve_scope(scope, puzzle.side_to_move))


def default_catalog_path() -> Path:
    return Path(__file__).with_name("data") / "hanging-default.json"


def curated_packages_dir() -> Path:
    return Path(__file__).with_name("data") / "packages"


def default_tactics_catalog_path() -> Path:
    """Default tactics package, still exposed for local/test convenience."""
    return curated_packages_dir() / "tri-band-tactics.json"


class PackageRegistry:
    """Discovers and loads tactics catalogs from a curated dir and a user dir.

    Curated packages ship in the source tree. User packages are written to a
    runtime-writable directory and rescanned on each `slugs()` / `metadata()`
    call so newly-saved packages appear without a server restart.
    """

    def __init__(self, curated_dir: Path, user_dir: Path) -> None:
        self.curated_dir = curated_dir
        self.user_dir = user_dir
        self._catalogs: dict[str, PuzzleCatalog] = {}
        self._paths: dict[str, Path] = {}
        self._kinds: dict[str, str] = {}
        self._mtimes: dict[Path, float] = {}
        self._errors: dict[Path, str] = {}
        self.refresh()

    def refresh(self) -> None:
        self._scan(self.curated_dir, "curated")
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self._scan(self.user_dir, "user")
        # Drop catalogs whose files have vanished.
        for slug in list(self._paths):
            if not self._paths[slug].exists():
                self._catalogs.pop(slug, None)
                self._paths.pop(slug, None)
                self._kinds.pop(slug, None)

    def _scan(self, directory: Path, kind: str) -> None:
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.json")):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if self._mtimes.get(path) == mtime and any(
                s for s, p in self._paths.items() if p == path
            ):
                continue
            try:
                # Tactics catalogs don't need the hanging-piece invariant; only
                # the hanging trainer's catalog enforces it (loaded separately).
                catalog = PuzzleCatalog.load(path, require_hanging=False)
            except CatalogError as exc:
                self._errors[path] = str(exc)
                continue
            slug = catalog.slug
            self._catalogs[slug] = catalog
            self._paths[slug] = path
            self._kinds[slug] = kind
            self._mtimes[path] = mtime
            self._errors.pop(path, None)

    def slugs(self) -> list[str]:
        self.refresh()
        curated = sorted(s for s in self._catalogs if self._kinds.get(s) == "curated")
        user = sorted(s for s in self._catalogs if self._kinds.get(s) == "user")
        return curated + user

    def get(self, slug: str) -> PuzzleCatalog:
        self.refresh()
        try:
            return self._catalogs[slug]
        except KeyError as exc:
            raise CatalogError(f"unknown package: {slug}") from exc

    def metadata(self, slug: str) -> dict[str, Any]:
        catalog = self.get(slug)
        return {
            **catalog.package,
            "count": catalog.target_count,
            "path": str(self._paths[slug]),
        }

    def kind(self, slug: str) -> str:
        self.get(slug)
        return self._kinds[slug]

    def register_user_package(self, catalog: PuzzleCatalog, path: Path) -> None:
        slug = catalog.slug
        self._catalogs[slug] = catalog
        self._paths[slug] = path
        self._kinds[slug] = "user"
        with contextlib.suppress(OSError):
            self._mtimes[path] = path.stat().st_mtime

    def remove(self, slug: str) -> None:
        if self._kinds.get(slug) != "user":
            raise CatalogError(f"cannot delete curated package: {slug}")
        path = self._paths[slug]
        try:
            path.unlink()
        except OSError as exc:
            raise CatalogError(f"unable to delete package file: {exc}") from exc
        self._catalogs.pop(slug, None)
        self._paths.pop(slug, None)
        self._kinds.pop(slug, None)
        self._mtimes.pop(path, None)
