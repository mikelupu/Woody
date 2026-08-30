"""Curate a tactics catalog: 100 middlegame fork/pin/skewer puzzles, tri-band rating.

Reuses the streaming reader, reconstruction, classification, and atomic-write patterns
from ``hanging_piece_trainer.curation`` and ``hanging_piece_trainer.catalog``.

Rating bands (inclusive):
    low    rating <= 1400   -> 34 puzzles
    medium 1401..1900       -> 33 puzzles
    hard   rating >= 1901   -> 33 puzzles
"""

from __future__ import annotations

import argparse
import csv
import sys
from itertools import chain
from pathlib import Path
from typing import Any

from hanging_piece_trainer.catalog import RULES_VERSION, SCHEMA_VERSION, checksum
from hanging_piece_trainer.curation import (
    LICHESS_FIELDS,
    _atomic_write_catalog,
    hash_rank,
    open_source,
    source_checksum,
)
from hanging_piece_trainer.domain import Color, DomainError, classify, reconstruct

BANDS: tuple[tuple[str, int, int, int], ...] = (
    ("low", 0, 1400, 34),
    ("medium", 1401, 1900, 33),
    ("hard", 1901, 10_000, 33),
)
TOTAL = sum(size for _, _, _, size in BANDS)
REQUIRED_THEMES = ("middlegame",)
ANY_OF_THEMES = ("fork", "pin", "skewer")


def band_for(rating: int) -> str | None:
    for name, low, high, _ in BANDS:
        if low <= rating <= high:
            return name
    return None


def curate(
    source: Path,
    output: Path,
    *,
    seed: int,
    source_url: str,
    source_name: str | None = None,
    expected_source_sha256: str | None = None,
    progress_every: int = 250_000,
) -> dict[str, Any]:
    pools: dict[str, list[dict[str, Any]]] = {name: [] for name, *_ in BANDS}
    pool_sizes = {name: size for name, _, _, size in BANDS}
    selected_ids: set[str] = set()
    scanned = 0
    evaluated = 0

    with open_source(source) as stream:
        reader = csv.reader(stream)
        required = {"PuzzleId", "FEN", "Moves", "Rating", "Themes"}
        try:
            first_row = next(reader)
        except StopIteration as exc:
            raise RuntimeError("empty Lichess CSV") from exc
        if required <= set(first_row):
            fieldnames = tuple(first_row)
            rows = reader
        else:
            if len(first_row) < 9:
                raise RuntimeError("unsupported Lichess CSV schema")
            fieldnames = LICHESS_FIELDS
            rows = chain((first_row,), reader)
        if not required <= set(fieldnames):
            raise RuntimeError("unsupported Lichess CSV schema")

        any_of = set(ANY_OF_THEMES)
        for values in rows:
            scanned += 1
            if progress_every and scanned % progress_every == 0:
                print(
                    f"scanned {scanned:,} rows; {evaluated:,} eligible candidates evaluated",
                    file=sys.stderr,
                )
            row = dict(zip(fieldnames, values, strict=False))
            puzzle_id = row["PuzzleId"].strip()
            if not puzzle_id or puzzle_id in selected_ids:
                continue
            themes = tuple(row["Themes"].split())
            if not all(tag in themes for tag in REQUIRED_THEMES):
                continue
            if not any_of.intersection(themes):
                continue
            moves = row["Moves"].split()
            if not moves:
                continue
            try:
                rating = int(row["Rating"])
            except ValueError:
                continue
            band = band_for(rating)
            if band is None:
                continue
            selection_rank = hash_rank(seed, puzzle_id)
            pool = pools[band]
            capacity = pool_sizes[band]
            worst_index: int | None = None
            if len(pool) >= capacity:
                worst_index = max(range(len(pool)), key=lambda i: pool[i]["_selection_rank"])
                if selection_rank >= pool[worst_index]["_selection_rank"]:
                    continue
            try:
                position = reconstruct(row["FEN"], moves[0])
                answers = {color: classify(position.fen, color) for color in Color}
            except (DomainError, TypeError, ValueError):
                continue
            if not answers[position.side_to_move].hanging:
                continue
            evaluated += 1
            candidate = {
                "_selection_rank": selection_rank,
                "puzzle_id": puzzle_id,
                "source_url": f"https://lichess.org/training/{puzzle_id}",
                "source_fen": row["FEN"],
                "first_move_uci": moves[0],
                "presented_fen": position.fen,
                "side_to_move": position.side_to_move.value,
                "rating": rating,
                "themes": sorted(themes),
                "answers_by_color": {color.value: answers[color].to_dict() for color in Color},
                "solution_moves_uci": moves[1:],
            }
            if len(pool) < capacity:
                pool.append(candidate)
                selected_ids.add(puzzle_id)
                continue
            assert worst_index is not None
            selected_ids.remove(pool[worst_index]["puzzle_id"])
            pool[worst_index] = candidate
            selected_ids.add(puzzle_id)

    print(
        f"scanned {scanned:,} rows; {evaluated:,} eligible candidates evaluated",
        file=sys.stderr,
    )
    shortages = [
        (name, len(pools[name]), pool_sizes[name])
        for name, *_ in BANDS
        if len(pools[name]) < pool_sizes[name]
    ]
    if shortages:
        detail = ", ".join(f"{name}: {have}/{want}" for name, have, want in shortages)
        raise RuntimeError(f"insufficient eligible puzzles per band ({detail})")

    combined: list[dict[str, Any]] = []
    for name, *_ in BANDS:
        combined.extend(pools[name])
    for candidate in combined:
        del candidate["_selection_rank"]
    selected = sorted(combined, key=lambda item: item["puzzle_id"])
    if len(selected) != TOTAL:
        raise RuntimeError(f"expected {TOTAL} puzzles, got {len(selected)}")

    actual_source_sha256 = source_checksum(source)
    if expected_source_sha256 and actual_source_sha256 != expected_source_sha256:
        raise RuntimeError("source snapshot checksum mismatch")

    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "source": {
            "name": source_name or source.name,
            "url": source_url,
            "sha256": actual_source_sha256,
        },
        "selection_seed": seed,
        "puzzles": selected,
    }
    data["catalog_checksum"] = checksum(data)
    _atomic_write_catalog(output, data)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--source-url", default="https://database.lichess.org/lichess_db_puzzle.csv.zst"
    )
    parser.add_argument("--source-name")
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--progress-every", type=int, default=250_000)
    args = parser.parse_args(argv)
    try:
        data = curate(
            args.source,
            args.output,
            seed=args.seed,
            source_url=args.source_url,
            source_name=args.source_name,
            expected_source_sha256=args.expected_source_sha256,
            progress_every=args.progress_every,
        )
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(data['puzzles'])} puzzles to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
