"""Framework-independent chess reconstruction and classification rules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

import chess


class DomainError(ValueError):
    """A stable user-input or chess-domain validation failure."""


class Color(StrEnum):
    WHITE = "white"
    BLACK = "black"

    @property
    def chess_color(self) -> chess.Color:
        return self is Color.WHITE

    @classmethod
    def from_chess(cls, value: chess.Color) -> Color:
        return cls.WHITE if value else cls.BLACK


class Scope(StrEnum):
    SIDE_TO_MOVE = "side_to_move"
    WHITE = "white"
    BLACK = "black"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class PresentedPosition:
    fen: str
    side_to_move: Color


@dataclass(frozen=True, slots=True)
class Classification:
    undefended: frozenset[str]
    hanging: frozenset[str]

    def __post_init__(self) -> None:
        if not self.hanging <= self.undefended:
            raise DomainError("hanging squares must be a subset of undefended squares")

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "undefended": sorted(self.undefended),
            "hanging": sorted(self.hanging),
        }


@dataclass(frozen=True, slots=True)
class Feedback:
    correct: frozenset[str]
    missed: frozenset[str]
    incorrect: frozenset[str]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "correct": sorted(self.correct),
            "missed": sorted(self.missed),
            "incorrect": sorted(self.incorrect),
        }


def normalize_squares(values: Iterable[str]) -> frozenset[str]:
    squares: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value not in chess.SQUARE_NAMES:
            raise DomainError(f"invalid square: {value!r}")
        squares.add(value)
    return frozenset(squares)


def board_from_fen(fen: str) -> chess.Board:
    try:
        board = chess.Board(fen)
    except (TypeError, ValueError) as exc:
        raise DomainError("invalid FEN") from exc
    if not board.is_valid():
        raise DomainError("invalid standard chess position")
    return board


def reconstruct(source_fen: str, first_move_uci: str) -> PresentedPosition:
    board = board_from_fen(source_fen)
    try:
        move = chess.Move.from_uci(first_move_uci)
    except (TypeError, ValueError) as exc:
        raise DomainError("invalid UCI move") from exc
    if move not in board.legal_moves:
        raise DomainError("illegal first move")
    board.push(move)
    if not board.is_valid():
        raise DomainError("move produced an invalid position")
    return PresentedPosition(fen=board.fen(), side_to_move=Color.from_chess(board.turn))


def classify(fen: str, color: Color) -> Classification:
    """Classify non-king pieces using geometric, pin-agnostic attack maps."""
    board = board_from_fen(fen)
    own = color.chess_color
    undefended: set[str] = set()
    hanging: set[str] = set()
    for square, piece in board.piece_map().items():
        if piece.color != own or piece.piece_type == chess.KING:
            continue
        defenders = board.attackers(own, square)
        attackers = board.attackers(not own, square)
        name = chess.square_name(square)
        if not defenders:
            undefended.add(name)
            if attackers:
                hanging.add(name)
    return Classification(frozenset(undefended), frozenset(hanging))


def resolve_scope(scope: Scope, side_to_move: Color) -> tuple[Color, ...]:
    if scope is Scope.SIDE_TO_MOVE:
        return (side_to_move,)
    if scope is Scope.WHITE:
        return (Color.WHITE,)
    if scope is Scope.BLACK:
        return (Color.BLACK,)
    return (Color.WHITE, Color.BLACK)


def union_classifications(
    answers: dict[Color, Classification], colors: Iterable[Color]
) -> Classification:
    selected = tuple(colors)
    return Classification(
        frozenset().union(*(answers[color].undefended for color in selected)),
        frozenset().union(*(answers[color].hanging for color in selected)),
    )


def compare(expected: frozenset[str], submitted: frozenset[str]) -> Feedback:
    return Feedback(
        correct=expected & submitted,
        missed=expected - submitted,
        incorrect=submitted - expected,
    )


def exact_hanging_score(expected: frozenset[str], submitted: frozenset[str]) -> bool:
    return expected == submitted
