"""Generate a deterministic offline development catalog without external puzzle data.

The resulting positions exercise the complete application, but release builds should replace this
artifact by running ``hpt-curate build`` against an explicitly acquired Lichess snapshot.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import chess

from hanging_piece_trainer.catalog import CATALOG_SIZE, RULES_VERSION, SCHEMA_VERSION, checksum
from hanging_piece_trainer.domain import Color, classify


def generate() -> dict:
    rng = random.Random(20260809)
    records = []
    seen_fens: set[str] = set()
    game = 0
    while len(records) < CATALOG_SIZE:
        game += 1
        board = chess.Board()
        for ply in range(rng.randint(28, 90)):
            legal = list(board.legal_moves)
            if not legal or board.is_game_over():
                break
            source_fen = board.fen()
            move = rng.choice(legal)
            board.push(move)
            if ply < 16 or board.fen() in seen_fens or not board.is_valid():
                continue
            side = Color.from_chess(board.turn)
            answers = {color: classify(board.fen(), color) for color in Color}
            if not answers[side].hanging:
                continue
            seen_fens.add(board.fen())
            number = len(records) + 1
            records.append(
                {
                    "puzzle_id": f"DEV{number:04d}",
                    "source_url": "development://synthetic-position",
                    "source_fen": source_fen,
                    "first_move_uci": move.uci(),
                    "presented_fen": board.fen(),
                    "side_to_move": side.value,
                    "rating": 1000 + (game * 37 + ply * 11) % 1400,
                    "themes": ["development", "middlegame"],
                    "answers_by_color": {color.value: answers[color].to_dict() for color in Color},
                }
            )
            if len(records) >= CATALOG_SIZE:
                break
    data = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "source": {
            "name": "deterministic development positions",
            "url": "development://synthetic-position",
            "sha256": "not-applicable",
        },
        "selection_seed": 20260809,
        "puzzles": records,
    }
    data["catalog_checksum"] = checksum(data)
    return data


if __name__ == "__main__":
    destination = Path("src/hanging_piece_trainer/data/puzzles.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(generate(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {CATALOG_SIZE} deterministic development positions to {destination}")
