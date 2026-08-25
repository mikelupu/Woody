"""SQLite-backed append-only attempt ledger and derived progress queries."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class RepositoryError(RuntimeError):
    """Progress storage could not complete a requested operation."""


class ProgressRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_meta "
                    "(singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
                    "version INTEGER NOT NULL)"
                )
                row = connection.execute(
                    "SELECT version FROM schema_meta WHERE singleton = 1"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO schema_meta(singleton, version) VALUES (1, ?)",
                        (SCHEMA_VERSION,),
                    )
                elif row["version"] != SCHEMA_VERSION:
                    raise RepositoryError("unsupported progress schema version")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS attempts (
                        attempt_id TEXT PRIMARY KEY,
                        puzzle_id TEXT NOT NULL,
                        presented_fen TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        effective_colors TEXT NOT NULL,
                        submitted_undefended TEXT NOT NULL,
                        submitted_hanging TEXT NOT NULL,
                        expected_undefended TEXT NOT NULL,
                        expected_hanging TEXT NOT NULL,
                        feedback TEXT NOT NULL,
                        correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
                        point_awarded INTEGER NOT NULL CHECK (point_awarded IN (0, 1)),
                        completion_ms INTEGER NOT NULL CHECK (completion_ms >= 0),
                        submitted_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        rules_version TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS attempts_submitted_at_idx "
                    "ON attempts(submitted_at DESC, attempt_id DESC)"
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS solve_attempts (
                        attempt_id TEXT PRIMARY KEY,
                        puzzle_id TEXT NOT NULL,
                        presented_fen TEXT NOT NULL,
                        submitted_moves TEXT NOT NULL,
                        expected_moves TEXT NOT NULL,
                        wrong_moves INTEGER NOT NULL CHECK (wrong_moves >= 0),
                        completed INTEGER NOT NULL CHECK (completed IN (0, 1)),
                        point_awarded INTEGER NOT NULL CHECK (point_awarded IN (0, 1)),
                        completion_ms INTEGER NOT NULL CHECK (completion_ms >= 0),
                        submitted_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        rules_version TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS solve_attempts_submitted_at_idx "
                    "ON solve_attempts(submitted_at DESC, attempt_id DESC)"
                )
                # Migrate older solve_attempts to carry batch context.
                for ddl in (
                    "ALTER TABLE solve_attempts ADD COLUMN batch_index INTEGER",
                    "ALTER TABLE solve_attempts ADD COLUMN cycle INTEGER",
                ):
                    with contextlib.suppress(sqlite3.OperationalError):
                        connection.execute(ddl)
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tactics_batches (
                        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        batch_index INTEGER NOT NULL,
                        cycle INTEGER NOT NULL,
                        completed_at TEXT NOT NULL,
                        points_earned INTEGER NOT NULL CHECK (points_earned >= 0),
                        points_possible INTEGER NOT NULL CHECK (points_possible >= 0),
                        puzzles_solved INTEGER NOT NULL CHECK (puzzles_solved >= 0),
                        puzzle_ids TEXT NOT NULL,
                        per_puzzle_points TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        rules_version TEXT NOT NULL,
                        UNIQUE (batch_index, cycle)
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS tactics_batches_completed_at_idx "
                    "ON tactics_batches(completed_at DESC, row_id DESC)"
                )
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to initialize progress database") from exc

    def commit_attempt(self, attempt: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Insert an attempt atomically or return the existing idempotent result."""
        columns = (
            "attempt_id",
            "puzzle_id",
            "presented_fen",
            "scope",
            "effective_colors",
            "submitted_undefended",
            "submitted_hanging",
            "expected_undefended",
            "expected_hanging",
            "feedback",
            "correct",
            "point_awarded",
            "completion_ms",
            "submitted_at",
            "schema_version",
            "rules_version",
        )
        values = [
            json.dumps(attempt[name], sort_keys=True)
            if isinstance(attempt[name], dict | list)
            else attempt[name]
            for name in columns
        ]
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id = ?", (attempt["attempt_id"],)
                ).fetchone()
                if existing is not None:
                    return self._decode(existing), False
                placeholders = ", ".join("?" for _ in columns)
                connection.execute(
                    f"INSERT INTO attempts ({', '.join(columns)}) VALUES ({placeholders})",
                    values,
                )
                row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id = ?", (attempt["attempt_id"],)
                ).fetchone()
                if row is None:
                    raise RepositoryError("attempt disappeared during commit")
                return self._decode(row), True
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to commit attempt") from exc

    def get_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)
                ).fetchone()
            return self._decode(row) if row is not None else None
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to read attempt") from exc

    def history(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0:
            raise RepositoryError("invalid history bounds")
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM attempts ORDER BY submitted_at DESC, attempt_id DESC "
                    "LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [self._decode(row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to read attempt history") from exc

    def stats(self) -> dict[str, int | float | None]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT point_awarded, completion_ms FROM attempts "
                    "ORDER BY submitted_at ASC, attempt_id ASC"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to derive progress statistics") from exc
        points = [int(row["point_awarded"]) for row in rows]
        durations = [int(row["completion_ms"]) for row in rows]
        current = 0
        best = 0
        for point in points:
            current = current + 1 if point else 0
            best = max(best, current)
        attempts = len(points)
        return {
            "attempts": attempts,
            "score": sum(points),
            "accuracy": (sum(points) / attempts) if attempts else 0.0,
            "current_streak": current,
            "best_streak": best,
            "average_completion_ms": (sum(durations) / attempts) if attempts else None,
            "most_recent_completion_ms": durations[-1] if durations else None,
        }

    def commit_solve_attempt(self, attempt: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        columns = (
            "attempt_id",
            "puzzle_id",
            "presented_fen",
            "submitted_moves",
            "expected_moves",
            "wrong_moves",
            "completed",
            "point_awarded",
            "completion_ms",
            "submitted_at",
            "schema_version",
            "rules_version",
            "batch_index",
            "cycle",
        )
        attempt = {
            **attempt,
            "batch_index": attempt.get("batch_index"),
            "cycle": attempt.get("cycle"),
        }
        values = [
            json.dumps(attempt[name], sort_keys=True)
            if isinstance(attempt[name], dict | list)
            else attempt[name]
            for name in columns
        ]
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM solve_attempts WHERE attempt_id = ?", (attempt["attempt_id"],)
                ).fetchone()
                if existing is not None:
                    return self._decode_solve(existing), False
                placeholders = ", ".join("?" for _ in columns)
                connection.execute(
                    f"INSERT INTO solve_attempts ({', '.join(columns)}) VALUES ({placeholders})",
                    values,
                )
                row = connection.execute(
                    "SELECT * FROM solve_attempts WHERE attempt_id = ?", (attempt["attempt_id"],)
                ).fetchone()
                if row is None:
                    raise RepositoryError("solve attempt disappeared during commit")
                return self._decode_solve(row), True
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to commit solve attempt") from exc

    def solve_history(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0:
            raise RepositoryError("invalid history bounds")
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM solve_attempts ORDER BY submitted_at DESC, attempt_id DESC "
                    "LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [self._decode_solve(row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to read solve attempt history") from exc

    def solve_stats(self) -> dict[str, int | float | None]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT point_awarded, completion_ms FROM solve_attempts "
                    "WHERE completed = 1 "
                    "ORDER BY submitted_at ASC, attempt_id ASC"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to derive solve statistics") from exc
        points = [int(row["point_awarded"]) for row in rows]
        durations = [int(row["completion_ms"]) for row in rows]
        current = 0
        best = 0
        for point in points:
            current = current + 1 if point else 0
            best = max(best, current)
        attempts = len(points)
        return {
            "attempts": attempts,
            "score": sum(points),
            "accuracy": (sum(points) / attempts) if attempts else 0.0,
            "current_streak": current,
            "best_streak": best,
            "average_completion_ms": (sum(durations) / attempts) if attempts else None,
            "most_recent_completion_ms": durations[-1] if durations else None,
        }

    @staticmethod
    def _decode_solve(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for name in ("submitted_moves", "expected_moves"):
            result[name] = json.loads(result[name])
        result["completed"] = bool(result["completed"])
        result["point_awarded"] = bool(result["point_awarded"])
        return result

    def solve_attempts_in_batch(self, batch_index: int, cycle: int) -> list[dict[str, Any]]:
        """Return `(puzzle_id, wrong_moves)` rows for solves in this batch/cycle."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT puzzle_id, wrong_moves, submitted_at FROM solve_attempts "
                    "WHERE batch_index = ? AND cycle = ? AND completed = 1 "
                    "ORDER BY submitted_at ASC",
                    (batch_index, cycle),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to read batch attempts") from exc

    def commit_tactics_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        columns = (
            "batch_index",
            "cycle",
            "completed_at",
            "points_earned",
            "points_possible",
            "puzzles_solved",
            "puzzle_ids",
            "per_puzzle_points",
            "schema_version",
            "rules_version",
        )
        values = [
            json.dumps(batch[name], sort_keys=True)
            if isinstance(batch[name], dict | list)
            else batch[name]
            for name in columns
        ]
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                placeholders = ", ".join("?" for _ in columns)
                cursor = connection.execute(
                    f"INSERT INTO tactics_batches ({', '.join(columns)}) VALUES ({placeholders})",
                    values,
                )
                row = connection.execute(
                    "SELECT * FROM tactics_batches WHERE row_id = ?", (cursor.lastrowid,)
                ).fetchone()
                if row is None:
                    raise RepositoryError("tactics batch disappeared during commit")
                return self._decode_tactics_batch(row)
        except sqlite3.IntegrityError as exc:
            raise RepositoryError("batch already committed for this cycle") from exc
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to commit tactics batch") from exc

    def tactics_batch_history(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0:
            raise RepositoryError("invalid history bounds")
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM tactics_batches "
                    "ORDER BY completed_at DESC, row_id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [self._decode_tactics_batch(row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to read tactics batch history") from exc

    def completed_batches(self, cycle: int) -> set[int]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT batch_index FROM tactics_batches WHERE cycle = ?", (cycle,)
                ).fetchall()
            return {int(row["batch_index"]) for row in rows}
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to read completed batches") from exc

    def current_cycle(self, batches_per_cycle: int) -> int:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT MAX(cycle) AS max_cycle FROM tactics_batches"
                ).fetchone()
            if row is None or row["max_cycle"] is None:
                return 0
            done = self.completed_batches(int(row["max_cycle"]))
            if len(done) >= batches_per_cycle:
                return int(row["max_cycle"]) + 1
            return int(row["max_cycle"])
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to determine current cycle") from exc

    def tactics_batch_stats(self) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT points_earned, points_possible FROM tactics_batches"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise RepositoryError("unable to derive tactics batch statistics") from exc
        earned = [int(row["points_earned"]) for row in rows]
        possible = [int(row["points_possible"]) for row in rows]
        batches = len(earned)
        return {
            "batches": batches,
            "total_earned": sum(earned),
            "total_possible": sum(possible),
            "average_earned": (sum(earned) / batches) if batches else 0.0,
            "best_batch": max(earned) if earned else 0,
        }

    @staticmethod
    def _decode_tactics_batch(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for name in ("puzzle_ids", "per_puzzle_points"):
            result[name] = json.loads(result[name])
        return result

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for name in (
            "effective_colors",
            "submitted_undefended",
            "submitted_hanging",
            "expected_undefended",
            "expected_hanging",
            "feedback",
        ):
            result[name] = json.loads(result[name])
        result["correct"] = bool(result["correct"])
        result["point_awarded"] = bool(result["point_awarded"])
        return result
