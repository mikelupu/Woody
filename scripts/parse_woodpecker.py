"""Parse the Woodpecker Method study PGN into a structured JSON puzzle set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import chess
import chess.pgn


def parse_pgn(pgn_path: Path) -> list[dict]:
    puzzles: list[dict] = []
    with pgn_path.open(encoding="utf-8") as stream:
        while True:
            game = chess.pgn.read_game(stream)
            if game is None:
                break
            headers = game.headers
            fen = headers.get("FEN")
            if not fen:
                continue
            board = chess.Board(fen)
            solution_san: list[str] = []
            solution_uci: list[str] = []
            for move in game.mainline_moves():
                solution_san.append(board.san(move))
                solution_uci.append(move.uci())
                board.push(move)
            puzzles.append(
                {
                    "chapter_name": headers.get("ChapterName", ""),
                    "chapter_url": headers.get("ChapterURL", ""),
                    "event": headers.get("Event", ""),
                    "fen": fen,
                    "side_to_move": "white" if chess.Board(fen).turn else "black",
                    "solution_san": solution_san,
                    "solution_uci": solution_uci,
                }
            )
    return puzzles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pgn", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    puzzles = parse_pgn(args.pgn)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(puzzles, indent=2) + "\n")
    print(f"wrote {len(puzzles)} puzzles to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
