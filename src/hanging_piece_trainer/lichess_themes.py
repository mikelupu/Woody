"""Canonical list of Lichess puzzle themes for the search UI.

Sourced from https://github.com/lichess-org/lila-tablebase and the puzzle-theme
tags encoded in the .zst dump. The list is used to seed the search builder's
theme dropdown; unknown themes are still searchable (free-text substring).
"""

from __future__ import annotations

CANONICAL_THEMES: tuple[str, ...] = (
    "advancedPawn",
    "advantage",
    "anastasiaMate",
    "arabianMate",
    "attackingF2F7",
    "attraction",
    "backRankMate",
    "bishopEndgame",
    "bodenMate",
    "capturingDefender",
    "castling",
    "clearance",
    "crushing",
    "defensiveMove",
    "deflection",
    "discoveredAttack",
    "doubleBishopMate",
    "doubleCheck",
    "dovetailMate",
    "endgame",
    "enPassant",
    "equality",
    "exposedKing",
    "fork",
    "hangingPiece",
    "hookMate",
    "interference",
    "intermezzo",
    "kingsideAttack",
    "knightEndgame",
    "long",
    "master",
    "masterVsMaster",
    "mate",
    "mateIn1",
    "mateIn2",
    "mateIn3",
    "mateIn4",
    "mateIn5",
    "middlegame",
    "oneMove",
    "opening",
    "pawnEndgame",
    "pin",
    "promotion",
    "queenEndgame",
    "queenRookEndgame",
    "queensideAttack",
    "quietMove",
    "rookEndgame",
    "sacrifice",
    "short",
    "skewer",
    "smotheredMate",
    "superGM",
    "trappedPiece",
    "underPromotion",
    "veryLong",
    "xRayAttack",
    "zugzwang",
)


PHASE_THEMES = {
    "opening": "opening",
    "middlegame": "middlegame",
    "endgame": "endgame",
}
