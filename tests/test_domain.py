from __future__ import annotations

import chess
import pytest

from hanging_piece_trainer.domain import (
    Classification,
    Color,
    DomainError,
    Scope,
    classify,
    compare,
    exact_hanging_score,
    normalize_squares,
    reconstruct,
    resolve_scope,
    union_classifications,
)


def test_reconstruct_applies_first_move_and_flips_turn() -> None:
    result = reconstruct(chess.STARTING_FEN, "e2e4")
    assert result.side_to_move is Color.BLACK
    assert chess.Board(result.fen).piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)


@pytest.mark.parametrize(
    "fen,move", [("bad", "e2e4"), (chess.STARTING_FEN, "bad"), (chess.STARTING_FEN, "e2e5")]
)
def test_reconstruct_rejects_invalid_input(fen: str, move: str) -> None:
    with pytest.raises(DomainError):
        reconstruct(fen, move)


def test_classification_finds_attacked_undefended_piece_and_excludes_king() -> None:
    result = classify("4k3/8/8/8/8/8/r7/R3K3 w - - 0 1", Color.WHITE)
    assert result.hanging == frozenset({"a1"})
    assert "e1" not in result.undefended


def test_pinned_piece_still_defends_geometrically() -> None:
    result = classify("4r1k1/8/8/8/8/8/N3R3/4K3 w - - 0 1", Color.WHITE)
    assert "a2" not in result.undefended


def test_scope_resolution_and_union() -> None:
    white = Classification(frozenset({"a1"}), frozenset({"a1"}))
    black = Classification(frozenset({"h8"}), frozenset())
    answers = {Color.WHITE: white, Color.BLACK: black}
    assert resolve_scope(Scope.SIDE_TO_MOVE, Color.BLACK) == (Color.BLACK,)
    assert resolve_scope(Scope.BOTH, Color.WHITE) == (Color.WHITE, Color.BLACK)
    assert union_classifications(answers, Color).undefended == frozenset({"a1", "h8"})


def test_feedback_and_exact_score() -> None:
    feedback = compare(frozenset({"a1", "b2"}), frozenset({"a1", "c3"}))
    assert feedback.correct == frozenset({"a1"})
    assert feedback.missed == frozenset({"b2"})
    assert feedback.incorrect == frozenset({"c3"})
    assert exact_hanging_score(frozenset({"a1"}), frozenset({"a1"}))
    assert not exact_hanging_score(frozenset({"a1"}), frozenset())


def test_normalize_squares_rejects_invalid_square() -> None:
    assert normalize_squares(["a1", "a1"]) == frozenset({"a1"})
    with pytest.raises(DomainError):
        normalize_squares(["z9"])


def test_classification_enforces_subset() -> None:
    with pytest.raises(DomainError):
        Classification(frozenset(), frozenset({"a1"}))
