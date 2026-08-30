"""Streaming Lichess puzzle curation and catalog validation command."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from typing import IO, Any

from .catalog import CATALOG_SIZE, RULES_VERSION, SCHEMA_VERSION, PuzzleCatalog, checksum
from .domain import Color, DomainError, classify, reconstruct

LICHESS_FIELDS = (
    "PuzzleId",
    "FEN",
    "Moves",
    "Rating",
    "RatingDeviation",
    "Popularity",
    "NbPlays",
    "Themes",
    "GameUrl",
    "OpeningTags",
    "DailyDate",
)


@contextmanager
def open_source(path: Path) -> Iterator[IO[str]]:
    if path.suffix == ".zst":
        try:
            import zstandard
        except ImportError as exc:
            raise RuntimeError("install the curation extra to read .zst files") from exc
        raw = path.open("rb")
        reader = zstandard.ZstdDecompressor().stream_reader(raw)
        text = io.TextIOWrapper(reader, encoding="utf-8", newline="")
        try:
            yield text
        finally:
            text.close()
            raw.close()
    else:
        with path.open(encoding="utf-8", newline="") as stream:
            yield stream


def source_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def hash_rank(seed: int, puzzle_id: str) -> int:
    """Deterministic 64-bit rank used to sample puzzles from a candidate pool."""
    return int.from_bytes(
        hashlib.blake2b(f"{seed}:{puzzle_id}".encode(), digest_size=8).digest(),
        "big",
    )


def _atomic_write_catalog(path: Path, data: dict[str, Any]) -> None:
    """Atomically write a catalog JSON to disk (tempfile → fsync → replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temporary:
            json.dump(data, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def curate(
    source: Path,
    output: Path,
    *,
    seed: int,
    source_url: str,
    source_name: str | None = None,
    expected_source_sha256: str | None = None,
    progress_every: int = 0,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Stream a Lichess snapshot and deterministically sample 100 eligible puzzles."""
    candidates: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    evaluated_eligible = 0
    scanned_count = 0
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
        for values in rows:
            scanned_count += 1
            if progress_every and progress and scanned_count % progress_every == 0:
                progress(scanned_count, evaluated_eligible)
            row = dict(zip(fieldnames, values, strict=False))
            puzzle_id = row["PuzzleId"].strip()
            themes = tuple(row["Themes"].split())
            moves = row["Moves"].split()
            if not puzzle_id or "middlegame" not in themes or not moves:
                continue
            if puzzle_id in selected_ids:
                continue
            selection_rank = hash_rank(seed, puzzle_id)
            worst_index: int | None = None
            if len(candidates) >= CATALOG_SIZE:
                worst_index = max(
                    range(len(candidates)), key=lambda index: candidates[index]["_selection_rank"]
                )
                if selection_rank >= candidates[worst_index]["_selection_rank"]:
                    continue
            try:
                position = reconstruct(row["FEN"], moves[0])
                answers = {color: classify(position.fen, color) for color in Color}
                rating = int(row["Rating"])
            except (DomainError, TypeError, ValueError):
                continue
            if not answers[position.side_to_move].hanging:
                continue
            evaluated_eligible += 1
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
            if len(candidates) < CATALOG_SIZE:
                candidates.append(candidate)
                selected_ids.add(puzzle_id)
                continue
            assert worst_index is not None
            selected_ids.remove(candidates[worst_index]["puzzle_id"])
            candidates[worst_index] = candidate
            selected_ids.add(puzzle_id)
    if progress:
        progress(scanned_count, evaluated_eligible)
    if len(candidates) < CATALOG_SIZE:
        raise RuntimeError(f"only {len(candidates)} eligible puzzles; need {CATALOG_SIZE}")
    for candidate in candidates:
        del candidate["_selection_rank"]
    selected = sorted(candidates, key=lambda item: item["puzzle_id"])
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("build", help="build a catalog from Lichess CSV")
    create.add_argument("source", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument("--seed", type=int, required=True)
    create.add_argument("--source-url", required=True)
    create.add_argument("--source-name")
    create.add_argument("--expected-source-sha256")
    create.add_argument("--progress-every", type=int, default=250_000)
    validate = subcommands.add_parser("validate", help="validate an existing catalog")
    validate.add_argument("catalog", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            catalog = PuzzleCatalog.load(args.catalog)
            print(f"valid catalog: {len(catalog._ids)} puzzles")
        else:
            data = curate(
                args.source,
                args.output,
                seed=args.seed,
                source_url=args.source_url,
                source_name=args.source_name,
                expected_source_sha256=args.expected_source_sha256,
                progress_every=args.progress_every,
                progress=lambda scanned, eligible: print(
                    f"scanned {scanned:,} rows; {eligible:,} eligible candidates evaluated",
                    file=sys.stderr,
                ),
            )
            print(f"wrote {len(data['puzzles'])} puzzles to {args.output}")
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
