from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import zstandard

from hanging_piece_trainer import curation
from hanging_piece_trainer.catalog import CATALOG_SIZE, checksum, default_catalog_path
from hanging_piece_trainer.domain import Classification, Color, PresentedPosition


def write_csv(
    path: Path,
    count: int,
    *,
    themes: str = "middlegame tactical",
    include_header: bool = True,
) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=curation.LICHESS_FIELDS)
        if include_header:
            writer.writeheader()
        for number in range(count):
            writer.writerow(
                {
                    "PuzzleId": f"TEST{number:04d}",
                    "FEN": "source fen",
                    "Moves": "e2e4 e7e5",
                    "Rating": str(1200 + number),
                    "Themes": themes,
                    "RatingDeviation": "75",
                    "Popularity": "90",
                    "NbPlays": "100",
                    "GameUrl": "https://lichess.org/example",
                    "OpeningTags": "",
                    "DailyDate": "",
                }
            )


def fake_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        curation,
        "reconstruct",
        lambda _fen, _move: PresentedPosition("4k3/8/8/8/8/8/r7/R3K3 w - - 0 1", Color.WHITE),
    )
    monkeypatch.setattr(
        curation,
        "classify",
        lambda _fen, color: Classification(
            frozenset({"a1" if color is Color.WHITE else "a2"}),
            frozenset({"a1" if color is Color.WHITE else "a2"}),
        ),
    )


def test_curate_writes_deterministic_atomic_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "catalog.json"
    write_csv(source, CATALOG_SIZE + 5)
    fake_rules(monkeypatch)
    progress: list[tuple[int, int]] = []
    data = curation.curate(
        source,
        output,
        seed=7,
        source_url="https://database.lichess.org/test.csv",
        progress_every=50,
        progress=lambda scanned, eligible: progress.append((scanned, eligible)),
    )
    assert len(data["puzzles"]) == CATALOG_SIZE
    assert data["catalog_checksum"] == checksum(data)
    assert json.loads(output.read_text()) == data
    assert data["puzzles"] == sorted(data["puzzles"], key=lambda item: item["puzzle_id"])
    assert progress[-1][0] == CATALOG_SIZE + 5
    assert progress[-1][1] >= CATALOG_SIZE
    repeated = curation.curate(
        source,
        tmp_path / "catalog-repeat.json",
        seed=7,
        source_url="https://database.lichess.org/test.csv",
    )
    assert [item["puzzle_id"] for item in repeated["puzzles"]] == [
        item["puzzle_id"] for item in data["puzzles"]
    ]


def test_curate_supports_official_headerless_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    write_csv(source, 1, include_header=False)
    fake_rules(monkeypatch)
    with pytest.raises(RuntimeError, match="only 1"):
        curation.curate(source, tmp_path / "out.json", seed=1, source_url="example")


def test_curate_failure_preserves_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "catalog.json"
    write_csv(source, 1)
    output.write_text("original")
    fake_rules(monkeypatch)
    with pytest.raises(RuntimeError, match="only 1"):
        curation.curate(source, output, seed=1, source_url="example")
    assert output.read_text() == "original"


def test_curate_rejects_unexpected_source_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "catalog.json"
    write_csv(source, CATALOG_SIZE)
    output.write_text("original")
    fake_rules(monkeypatch)
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        curation.curate(
            source,
            output,
            seed=1,
            source_url="example",
            expected_source_sha256="0" * 64,
        )
    assert output.read_text() == "original"


def test_curate_rejects_schema_and_skips_wrong_theme(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.csv"
    malformed.write_text("bad,headers\n1,2\n")
    with pytest.raises(RuntimeError, match="schema"):
        curation.curate(malformed, tmp_path / "out.json", seed=1, source_url="example")
    source = tmp_path / "source.csv"
    write_csv(source, 1, themes="opening")
    with pytest.raises(RuntimeError, match="only 0"):
        curation.curate(source, tmp_path / "out.json", seed=1, source_url="example")


def test_open_source_reads_zstandard(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv.zst"
    path.write_bytes(zstandard.ZstdCompressor().compress(b"heading\nvalue\n"))
    with curation.open_source(path) as stream:
        assert stream.read() == "heading\nvalue\n"


def test_curation_cli_validate_and_errors(tmp_path: Path, capsys) -> None:
    assert curation.main(["validate", str(default_catalog_path())]) == 0
    assert "valid catalog" in capsys.readouterr().out
    assert curation.main(["validate", str(tmp_path / "missing.json")]) == 1
    assert "error:" in capsys.readouterr().err
