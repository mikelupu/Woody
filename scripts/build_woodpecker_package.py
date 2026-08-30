"""Build a curated tactics package from the Woodpecker study JSON.

Reads `data/woodpecker-1-64.json` (produced by `parse_woodpecker.py`) and writes
a packages-schema catalog to `data/packages/woodpecker-method-1-60.json`.

Trims to 60 puzzles because the packages schema requires a positive multiple of 5
(so it can split into batches of 5). Puzzles are stored with `first_move_uci=""`
and `source_fen == presented_fen`, meaning the study position is presented
directly with no opponent setup move.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from hanging_piece_trainer.catalog import RULES_VERSION, SCHEMA_VERSION, checksum
from hanging_piece_trainer.curation import _atomic_write_catalog
from hanging_piece_trainer.domain import Color, classify

TARGET_COUNT = 60
SLUG = "woodpecker-method-1-60"
TITLE = "Woodpecker Method — Puzzles 1-60"
DESCRIPTION = (
    'First 60 puzzles from the Lichess study "Woodpecker Method Puzzles (1 - 64)" by zozchess111.'
)
STUDY_URL = "https://lichess.org/study/OavXzGxF"


def build(source_json: Path, output: Path) -> dict[str, Any]:
    entries = json.loads(source_json.read_text())
    if len(entries) < TARGET_COUNT:
        raise RuntimeError(f"need {TARGET_COUNT} puzzles, source has {len(entries)}")

    puzzles: list[dict[str, Any]] = []
    seen_fens: set[str] = set()
    for entry in entries:
        if len(puzzles) >= TARGET_COUNT:
            break
        fen = entry["fen"]
        if fen in seen_fens:
            continue
        seen_fens.add(fen)
        index = len(puzzles) + 1
        answers = {color: classify(fen, color) for color in Color}
        puzzles.append(
            {
                "puzzle_id": f"woodpecker-{index:02d}",
                "source_url": entry["chapter_url"] or STUDY_URL,
                "source_fen": fen,
                "first_move_uci": "",
                "presented_fen": fen,
                "side_to_move": entry["side_to_move"],
                "rating": None,
                "themes": ["mate", "woodpecker"],
                "answers_by_color": {color.value: answers[color].to_dict() for color in Color},
                "solution_moves_uci": entry["solution_uci"],
            }
        )

    source_bytes = source_json.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()

    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "target_count": TARGET_COUNT,
        "source": {
            "name": source_json.name,
            "url": STUDY_URL,
            "sha256": source_sha,
        },
        "package": {
            "slug": SLUG,
            "title": TITLE,
            "description": DESCRIPTION,
            "kind": "curated",
            "created_at": "2026-08-29T00:00:00Z",
            "query": None,
        },
        "selection_seed": 0,
        "puzzles": puzzles,
    }
    data["catalog_checksum"] = checksum(data)
    _atomic_write_catalog(output, data)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("src/hanging_piece_trainer/data/woodpecker-1-64.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(f"src/hanging_piece_trainer/data/packages/{SLUG}.json"),
    )
    args = parser.parse_args(argv)
    data = build(args.source, args.output)
    print(f"wrote {len(data['puzzles'])} puzzles to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
