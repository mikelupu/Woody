"""Save-as-package flow: turn a SearchQuery result into a valid catalog JSON."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalog import (
    PACKAGE_KINDS,
    RESERVED_SLUGS,
    RULES_VERSION,
    SCHEMA_VERSION,
    SLUG_RE,
    CatalogError,
    PuzzleCatalog,
    checksum,
)
from .curation import _atomic_write_catalog
from .domain import Color, DomainError, classify, reconstruct
from .lichess_index import LichessIndex, SearchQuery


class SearchError(RuntimeError):
    """A save-as-package request failed for a caller-visible reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


ALLOWED_COUNTS = (10, 20, 50, 100, 200)


def _validate_slug(slug: str, *, existing: set[str]) -> None:
    if not SLUG_RE.match(slug):
        raise SearchError("invalid_slug", f"slug must match {SLUG_RE.pattern}")
    if slug in RESERVED_SLUGS:
        raise SearchError("slug_reserved", f"slug {slug!r} is reserved by the system")
    if slug in existing:
        raise SearchError("slug_in_use", f"a package named {slug!r} already exists")


def _build_catalog_dict(
    slug: str,
    title: str,
    description: str,
    query: SearchQuery,
    puzzles: list[dict[str, Any]],
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "package": {
            "slug": slug,
            "title": title,
            "description": description,
            "kind": "user",
            "created_at": datetime.now(UTC).isoformat(),
            "query": dataclasses.asdict(query),
        },
        "source": {
            "name": "lichess_db_puzzle.csv.zst",
            "url": "https://database.lichess.org/lichess_db_puzzle.csv.zst",
            "sha256": None,
        },
        "selection_seed": query.seed,
        "target_count": len(puzzles),
        "puzzles": sorted(puzzles, key=lambda p: p["puzzle_id"]),
    }
    data["catalog_checksum"] = checksum(data)
    return data


def _puzzle_record_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Turn an indexed Lichess row into a schema-v2 puzzle record."""
    moves = row["moves"].split()
    if not moves:
        return None
    try:
        position = reconstruct(row["fen"], moves[0])
        answers = {color: classify(position.fen, color) for color in Color}
    except (DomainError, TypeError, ValueError):
        return None
    return {
        "puzzle_id": row["id"],
        "source_url": row.get("game_url") or f"https://lichess.org/training/{row['id']}",
        "source_fen": row["fen"],
        "first_move_uci": moves[0],
        "presented_fen": position.fen,
        "side_to_move": position.side_to_move.value,
        "rating": int(row["rating"]) if row.get("rating") is not None else None,
        "themes": sorted(row["themes"].split()) if isinstance(row.get("themes"), str) else [],
        "answers_by_color": {color.value: answers[color].to_dict() for color in Color},
        "solution_moves_uci": moves[1:],
    }


def save_search_as_package(
    index: LichessIndex,
    *,
    query: SearchQuery,
    slug: str,
    title: str,
    description: str,
    existing_slugs: set[str],
    output_dir: Path,
) -> tuple[Path, PuzzleCatalog]:
    """Deterministically sample puzzles matching `query`, write a valid
    catalog JSON, and return the on-disk path plus loaded PuzzleCatalog."""
    if query.target_count not in ALLOWED_COUNTS:
        raise SearchError(
            "invalid_count",
            f"target_count must be one of {ALLOWED_COUNTS}",
        )
    _validate_slug(slug, existing=existing_slugs)
    # Ask the index for up to 3x target so we can drop any failures.
    ranked = index.matching_ids_ranked(query, limit=query.target_count * 3)
    # Not enough candidates — take what we can, minimum 10.
    if len(ranked) < query.target_count and len(ranked) < 10:
        raise SearchError(
            "insufficient_matches",
            f"only {len(ranked)} matches; loosen filters or lower the count",
        )
    puzzles: list[dict[str, Any]] = []
    for row in ranked:
        record = _puzzle_record_from_row(row)
        if record is None:
            continue
        puzzles.append(record)
        if len(puzzles) >= query.target_count:
            break
    # Round down to a multiple of 5 (catalog invariant).
    usable = (len(puzzles) // 5) * 5
    if usable < 5:
        raise SearchError(
            "insufficient_matches",
            f"only {len(puzzles)} puzzles survived validation; need a multiple of 5",
        )
    puzzles = puzzles[:usable]

    data = _build_catalog_dict(slug, title, description, query, puzzles)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{slug}.json"
    if path.exists():
        raise SearchError("slug_in_use", f"file already exists at {path}")
    _atomic_write_catalog(path, data)
    try:
        catalog = PuzzleCatalog.load(path, require_hanging=False)
    except CatalogError as exc:
        path.unlink(missing_ok=True)
        raise SearchError("invalid_catalog", str(exc)) from exc
    return path, catalog


def query_from_payload(payload: dict[str, Any]) -> SearchQuery:
    """Parse an untrusted JSON payload into a validated SearchQuery."""
    if not isinstance(payload, dict):
        raise SearchError("invalid_request", "expected JSON object")

    def _tuple(key: str) -> tuple[str, ...]:
        raw = payload.get(key)
        if raw is None:
            return ()
        if isinstance(raw, str):
            raw = [item.strip() for item in raw.split(",") if item.strip()]
        if not isinstance(raw, list | tuple) or not all(isinstance(x, str) for x in raw):
            raise SearchError("invalid_request", f"{key} must be a list of strings")
        return tuple(item for item in raw if item)

    def _int_or_none(key: str) -> int | None:
        raw = payload.get(key)
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise SearchError("invalid_request", f"{key} must be an integer") from exc

    def _str_or_none(key: str) -> str | None:
        raw = payload.get(key)
        if raw is None or raw == "":
            return None
        return str(raw)

    phase = _str_or_none("phase")
    if phase not in (None, "opening", "middlegame", "endgame"):
        raise SearchError("invalid_request", "phase must be opening/middlegame/endgame")
    side = _str_or_none("side_to_move")
    if side not in (None, "white", "black"):
        raise SearchError("invalid_request", "side_to_move must be white/black")

    return SearchQuery(
        required_themes=_tuple("required_themes"),
        any_of_themes=_tuple("any_of_themes"),
        excluded_themes=_tuple("excluded_themes"),
        rating_min=_int_or_none("rating_min"),
        rating_max=_int_or_none("rating_max"),
        rating_deviation_max=_int_or_none("rating_deviation_max"),
        popularity_min=_int_or_none("popularity_min"),
        nb_plays_min=_int_or_none("nb_plays_min"),
        phase=phase,
        solution_plies_min=_int_or_none("solution_plies_min"),
        solution_plies_max=_int_or_none("solution_plies_max"),
        mate_in=_int_or_none("mate_in"),
        opening_tag=_str_or_none("opening_tag"),
        side_to_move=side,
        target_count=_int_or_none("target_count") or 50,
        seed=_int_or_none("seed") or 20260827,
    )


__all__ = [
    "ALLOWED_COUNTS",
    "PACKAGE_KINDS",
    "SearchError",
    "query_from_payload",
    "save_search_as_package",
]
