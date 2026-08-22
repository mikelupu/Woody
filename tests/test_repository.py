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


def test_unsupported_schema_is_not_replaced(tmp_path: Path) -> None:
    path = tmp_path / "progress.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE schema_meta(singleton INTEGER PRIMARY KEY, version INTEGER)")
    connection.execute("INSERT INTO schema_meta VALUES(1, 999)")
    connection.commit()
    connection.close()
    with pytest.raises(RepositoryError, match="unsupported"):
        ProgressRepository(path).initialize()
