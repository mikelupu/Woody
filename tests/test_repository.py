from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from hanging_piece_trainer.repository import ProgressRepository, RepositoryError


def attempt(identifier: str, point: bool, submitted_at: str, duration: int = 1000) -> dict:
    return {
        "attempt_id": identifier,
        "puzzle_id": "DEV0001",
        "presented_fen": "fen",
        "scope": "side_to_move",
        "effective_colors": ["white"],
        "submitted_undefended": [],
        "submitted_hanging": [],
        "expected_undefended": [],
        "expected_hanging": [],
        "feedback": {"hanging": {}},
        "correct": point,
        "point_awarded": point,
        "completion_ms": duration,
        "submitted_at": submitted_at,
        "schema_version": 1,
        "rules_version": "1.0.0",
    }


def test_repository_commit_replay_history_and_stats(tmp_path: Path) -> None:
    repository = ProgressRepository(tmp_path / "progress.sqlite3")
    repository.initialize()
    first, created = repository.commit_attempt(attempt("attempt-1", True, "2026-01-01T00:00:00Z"))
    assert created and first["point_awarded"]
    replay, created = repository.commit_attempt(attempt("attempt-1", False, "2027-01-01T00:00:00Z"))
    assert not created and replay["point_awarded"]
    assert repository.get_attempt("attempt-1")["point_awarded"]
    assert repository.get_attempt("missing") is None
    repository.commit_attempt(attempt("attempt-2", True, "2026-01-02T00:00:00Z", 3000))
    repository.commit_attempt(attempt("attempt-3", False, "2026-01-03T00:00:00Z", 2000))
    assert [row["attempt_id"] for row in repository.history(limit=2)] == ["attempt-3", "attempt-2"]
    assert repository.stats() == {
        "attempts": 3,
        "score": 2,
        "accuracy": 2 / 3,
        "current_streak": 0,
        "best_streak": 2,
        "average_completion_ms": 2000,
        "most_recent_completion_ms": 2000,
    }


def test_empty_stats(tmp_path: Path) -> None:
    repository = ProgressRepository(tmp_path / "progress.sqlite3")
    repository.initialize()
    assert repository.stats()["average_completion_ms"] is None


def test_invalid_history_bounds(tmp_path: Path) -> None:
    repository = ProgressRepository(tmp_path / "progress.sqlite3")
    repository.initialize()
    with pytest.raises(RepositoryError):
        repository.history(limit=0)


def test_bookmarks_crud_and_filter(tmp_path: Path) -> None:
    repository = ProgressRepository(tmp_path / "progress.sqlite3")
    repository.initialize()
    a = repository.add_bookmark(
        source_package="pkg-a",
        puzzle_id="P0001",
        tags=["endgame", "rook"],
        bookmarked_at="2026-01-01T00:00:00Z",
    )
    b = repository.add_bookmark(
        source_package="pkg-a",
        puzzle_id="P0002",
        tags=["opening"],
        bookmarked_at="2026-01-02T00:00:00Z",
    )
    c = repository.add_bookmark(
        source_package="pkg-b",
        puzzle_id="P0001",
        tags=[],
        bookmarked_at="2026-01-03T00:00:00Z",
    )
    assert a["tags"] == ["endgame", "rook"]
    assert repository.count_bookmarks() == 3
    all_rows = repository.list_bookmarks()
    assert [row["bookmark_id"] for row in all_rows] == [
        c["bookmark_id"],
        b["bookmark_id"],
        a["bookmark_id"],
    ]
    endgame = repository.list_bookmarks(tag="endgame")
    assert [row["bookmark_id"] for row in endgame] == [a["bookmark_id"]]
    with pytest.raises(RepositoryError, match="already exists"):
        repository.add_bookmark(
            source_package="pkg-a",
            puzzle_id="P0001",
            tags=["dupe"],
            bookmarked_at="2026-01-04T00:00:00Z",
        )
    updated = repository.update_bookmark_tags(a["bookmark_id"], ["middlegame"])
    assert updated["tags"] == ["middlegame"]
    fetched = repository.get_bookmark_by_puzzle("pkg-a", "P0001")
    assert fetched is not None and fetched["tags"] == ["middlegame"]
    assert repository.get_bookmark_by_puzzle("pkg-a", "missing") is None
    assert repository.delete_bookmark(a["bookmark_id"]) is True
    assert repository.delete_bookmark(a["bookmark_id"]) is False
    assert repository.count_bookmarks() == 2


def test_unsupported_schema_is_not_replaced(tmp_path: Path) -> None:
    path = tmp_path / "progress.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE schema_meta(singleton INTEGER PRIMARY KEY, version INTEGER)")
    connection.execute("INSERT INTO schema_meta VALUES(1, 999)")
    connection.commit()
    connection.close()
    with pytest.raises(RepositoryError, match="unsupported"):
        ProgressRepository(path).initialize()
