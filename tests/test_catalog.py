from __future__ import annotations

import copy
import json

import pytest

from hanging_piece_trainer.catalog import (
    CatalogError,
    PuzzleCatalog,
    checksum,
    default_catalog_path,
)
from hanging_piece_trainer.domain import Scope


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(default_catalog_path().read_text())


def test_bundled_catalog_validates_and_public_view_hides_answers(data: dict) -> None:
    catalog = PuzzleCatalog(copy.deepcopy(data))
    puzzle = catalog.next()
    assert "answers_by_color" not in puzzle.public_dict()
    assert catalog.expected(puzzle.puzzle_id, Scope.SIDE_TO_MOVE).hanging
    assert data["source"]["url"].endswith("lichess_db_puzzle.csv.zst")
    assert all(
        record["source_url"] == f"https://lichess.org/training/{record['puzzle_id']}"
        for record in data["puzzles"]
    )


def test_next_avoids_previous(data: dict) -> None:
    catalog = PuzzleCatalog(copy.deepcopy(data), verify_answers=False)
    first = catalog.next()
    assert catalog.next(first.puzzle_id).puzzle_id != first.puzzle_id


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda value: value.update(schema_version=99), "schema"),
        (lambda value: value.update(rules_version="old"), "rules"),
        (lambda value: value["puzzles"].pop(), "exactly"),
    ],
)
def test_catalog_rejects_incompatible_content(data: dict, mutation, message: str) -> None:
    changed = copy.deepcopy(data)
    mutation(changed)
    changed["catalog_checksum"] = checksum(changed)
    with pytest.raises(CatalogError, match=message):
        PuzzleCatalog(changed, verify_answers=False)


def test_catalog_rejects_checksum_mismatch(data: dict) -> None:
    changed = copy.deepcopy(data)
    changed["selection_seed"] = -1
    with pytest.raises(CatalogError, match="checksum"):
        PuzzleCatalog(changed, verify_answers=False)


def test_catalog_rejects_presented_fen_that_does_not_match_source(data: dict) -> None:
    changed = copy.deepcopy(data)
    changed["puzzles"][0]["presented_fen"] = changed["puzzles"][1]["presented_fen"]
    changed["puzzles"][0]["side_to_move"] = changed["puzzles"][1]["side_to_move"]
    changed["catalog_checksum"] = checksum(changed)
    with pytest.raises(CatalogError, match="presented FEN mismatch"):
        PuzzleCatalog(changed, verify_answers=False)
