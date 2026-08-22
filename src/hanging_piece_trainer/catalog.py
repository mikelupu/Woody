"""Immutable puzzle catalog loading, validation, and answer-safe projection."""

from __future__ import annotations

import hashlib
import json
import random
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

    def public_dict(self) -> dict[str, Any]:
        return {
            "puzzle_id": self.puzzle_id,
            "source_url": self.source_url,
            "presented_fen": self.presented_fen,
            "side_to_move": self.side_to_move.value,
            "rating": self.rating,
            "themes": list(self.themes),
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
        )
    except (KeyError, TypeError, ValueError, DomainError) as exc:
        raise CatalogError("invalid puzzle record") from exc
    board = board_from_fen(puzzle.presented_fen)
    if Color.from_chess(board.turn) is not puzzle.side_to_move:
        raise CatalogError(f"side-to-move mismatch for {puzzle.puzzle_id}")
    try:
        reconstructed = reconstruct(puzzle.source_fen, puzzle.first_move_uci)
    except DomainError as exc:
        raise CatalogError(f"source reconstruction failed for {puzzle.puzzle_id}") from exc
    if reconstructed.fen != puzzle.presented_fen:
        raise CatalogError(f"presented FEN mismatch for {puzzle.puzzle_id}")
    if "middlegame" not in puzzle.themes:
        raise CatalogError(f"missing middlegame theme for {puzzle.puzzle_id}")
    return puzzle


class PuzzleCatalog:
    def __init__(self, data: dict[str, Any], *, verify_answers: bool = True) -> None:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise CatalogError("unsupported catalog schema version")
        if data.get("rules_version") != RULES_VERSION:
            raise CatalogError("unsupported rules version")
        if data.get("catalog_checksum") != checksum(data):
            raise CatalogError("catalog checksum mismatch")
        raw_puzzles = data.get("puzzles")
        if not isinstance(raw_puzzles, list) or len(raw_puzzles) != CATALOG_SIZE:
            raise CatalogError(f"catalog must contain exactly {CATALOG_SIZE} puzzles")
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
                if not puzzle.answers[puzzle.side_to_move].hanging:
                    raise CatalogError(f"side to move has no hanging piece: {puzzle.puzzle_id}")
        self.metadata = {key: value for key, value in data.items() if key != "puzzles"}
        self._puzzles = {puzzle.puzzle_id: puzzle for puzzle in puzzles}
        self._ids = tuple(self._puzzles)

    @classmethod
    def load(cls, path: Path, *, verify_answers: bool = True) -> PuzzleCatalog:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"unable to read catalog: {path}") from exc
        return cls(data, verify_answers=verify_answers)

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
    return Path(__file__).with_name("data") / "puzzles.json"


def default_tactics_catalog_path() -> Path:
    return Path(__file__).with_name("data") / "puzzles_tactics.json"
