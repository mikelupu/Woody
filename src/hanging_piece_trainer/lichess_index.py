"""Local SQLite index over the Lichess puzzle .zst dump.

The index is built once from `data/source/lichess_db_puzzle.csv.zst` and stored
at `data/lichess_index.sqlite3` (git-ignored). Live search + preview queries
run against the index so filter changes stay interactive (<100 ms per query).
"""

from __future__ import annotations

import contextlib
import csv
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import Any

from .curation import LICHESS_FIELDS, open_source
from .lichess_themes import PHASE_THEMES

INDEX_SCHEMA_VERSION = 1
BATCH_SIZE = 10_000


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Filter definition for the search builder. All fields optional."""

    required_themes: tuple[str, ...] = ()
    any_of_themes: tuple[str, ...] = ()
    excluded_themes: tuple[str, ...] = ()
    rating_min: int | None = None
    rating_max: int | None = None
    rating_deviation_max: int | None = None
    popularity_min: int | None = None
    nb_plays_min: int | None = None
    phase: str | None = None
    solution_plies_min: int | None = None
    solution_plies_max: int | None = None
    mate_in: int | None = None
    opening_tag: str | None = None
    side_to_move: str | None = None
    target_count: int = 50
    seed: int = 20260827


@dataclass(slots=True)
class SearchPreview:
    count: int
    sample: list[dict[str, Any]] = field(default_factory=list)
    rating_histogram: list[int] = field(default_factory=lambda: [0] * 10)


def _derive_phase(themes: Iterable[str]) -> str | None:
    tags = set(themes)
    for phase, tag in PHASE_THEMES.items():
        if tag in tags:
            return phase
    return None


class LichessIndex:
    """SQLite-backed queryable index of the full Lichess puzzle dump."""

    def __init__(self, db_path: Path, *, source_path: Path | None = None) -> None:
        self.db_path = db_path
        self.source_path = source_path
        self._build_lock = threading.Lock()
        self._build_state: dict[str, Any] = {
            "running": False,
            "scanned": 0,
            "inserted": 0,
            "started_at": None,
            "error": None,
        }
        self._opening_tags_cache: list[str] | None = None

    # ─── Lifecycle ────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS puzzles (
                id TEXT PRIMARY KEY,
                fen TEXT NOT NULL,
                moves TEXT NOT NULL,
                rating INTEGER NOT NULL,
                rating_dev INTEGER NOT NULL,
                popularity INTEGER NOT NULL,
                nb_plays INTEGER NOT NULL,
                themes TEXT NOT NULL,
                game_url TEXT NOT NULL,
                opening_tags TEXT NOT NULL,
                solution_plies INTEGER NOT NULL,
                phase TEXT
            );
            CREATE INDEX IF NOT EXISTS puzzles_rating ON puzzles(rating);
            CREATE INDEX IF NOT EXISTS puzzles_popularity ON puzzles(popularity);
            CREATE INDEX IF NOT EXISTS puzzles_nb_plays ON puzzles(nb_plays);
            CREATE INDEX IF NOT EXISTS puzzles_phase ON puzzles(phase);
            CREATE INDEX IF NOT EXISTS puzzles_plies ON puzzles(solution_plies);
            """
        )

    def status(self) -> dict[str, Any]:
        if not self.db_path.exists():
            state = "missing"
            count = 0
        else:
            try:
                with self._connect() as connection:
                    self._create_schema(connection)
                    count = connection.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0]
                state = "ready" if count > 0 else "empty"
            except sqlite3.DatabaseError as exc:
                return {
                    "state": "corrupt",
                    "count": 0,
                    "error": str(exc),
                    "source_available": self.source_available(),
                }
        return {
            "state": "building" if self._build_state["running"] else state,
            "count": count,
            "scanned": self._build_state["scanned"],
            "inserted": self._build_state["inserted"],
            "started_at": self._build_state["started_at"],
            "error": self._build_state["error"],
            "source_available": self.source_available(),
            "source_path": str(self.source_path) if self.source_path else None,
        }

    def source_available(self) -> bool:
        return self.source_path is not None and self.source_path.exists()

    # ─── Building ─────────────────────────────────────────────────────────

    def build(
        self,
        source: Path | None = None,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """Synchronously rebuild the index. Raises RuntimeError if a build
        is already in progress."""
        if not self._build_lock.acquire(blocking=False):
            raise RuntimeError("index build already in progress")
        try:
            source = source or self.source_path
            if source is None or not source.exists():
                raise RuntimeError(f"Lichess source not found: {source}")
            self._build_state.update(
                running=True,
                scanned=0,
                inserted=0,
                started_at=time.time(),
                error=None,
            )
            try:
                self._build_impl(source, progress)
            except Exception as exc:
                self._build_state["error"] = str(exc)
                raise
            finally:
                self._build_state["running"] = False
        finally:
            self._build_lock.release()

    def _build_impl(self, source: Path, progress: Callable[[int, int], None] | None) -> None:
        self._opening_tags_cache = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            # Fresh rebuild — drop and recreate to avoid partial state.
            connection.execute("DROP TABLE IF EXISTS puzzles")
            self._create_schema(connection)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = OFF")
            connection.commit()

            batch: list[tuple[Any, ...]] = []
            with open_source(source) as stream:
                reader = csv.reader(stream)
                try:
                    first_row = next(reader)
                except StopIteration as exc:
                    raise RuntimeError("empty Lichess CSV") from exc
                required = {"PuzzleId", "FEN", "Moves", "Rating", "Themes"}
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
                    self._build_state["scanned"] += 1
                    row = dict(zip(fieldnames, values, strict=False))
                    puzzle_id = row.get("PuzzleId", "").strip()
                    if not puzzle_id:
                        continue
                    themes = row.get("Themes", "").split()
                    moves = row.get("Moves", "").split()
                    if not moves:
                        continue
                    try:
                        rating = int(row.get("Rating") or 0)
                        rating_dev = int(row.get("RatingDeviation") or 0)
                        popularity = int(row.get("Popularity") or 0)
                        nb_plays = int(row.get("NbPlays") or 0)
                    except ValueError:
                        continue
                    phase = _derive_phase(themes)
                    batch.append(
                        (
                            puzzle_id,
                            row.get("FEN", ""),
                            " ".join(moves),
                            rating,
                            rating_dev,
                            popularity,
                            nb_plays,
                            " ".join(themes),
                            row.get("GameUrl", ""),
                            row.get("OpeningTags", "") or "",
                            max(0, len(moves) - 1),
                            phase,
                        )
                    )
                    if len(batch) >= BATCH_SIZE:
                        self._flush_batch(connection, batch)
                        batch.clear()
                        if progress is not None:
                            progress(
                                self._build_state["scanned"],
                                self._build_state["inserted"],
                            )
                if batch:
                    self._flush_batch(connection, batch)
                    batch.clear()
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", str(INDEX_SCHEMA_VERSION)),
            )
            connection.commit()
            if progress is not None:
                progress(self._build_state["scanned"], self._build_state["inserted"])

    def _flush_batch(self, connection: sqlite3.Connection, batch: list[tuple[Any, ...]]) -> None:
        connection.executemany(
            "INSERT OR REPLACE INTO puzzles "
            "(id, fen, moves, rating, rating_dev, popularity, nb_plays, "
            "themes, game_url, opening_tags, solution_plies, phase) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
        connection.commit()
        self._build_state["inserted"] += len(batch)

    def build_async(self) -> bool:
        """Kick off a background build. Returns False if already running."""
        if self._build_state["running"]:
            return False
        thread = threading.Thread(
            target=self._safe_build,
            name="lichess-index-build",
            daemon=True,
        )
        thread.start()
        return True

    def _safe_build(self) -> None:
        # Async build wrapper — any failure is already recorded in _build_state.
        with contextlib.suppress(Exception):
            self.build()

    # ─── Querying ─────────────────────────────────────────────────────────

    def _where(self, query: SearchQuery) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for theme in query.required_themes:
            clauses.append("(' ' || themes || ' ') LIKE ?")
            params.append(f"% {theme} %")
        if query.any_of_themes:
            anys = " OR ".join("(' ' || themes || ' ') LIKE ?" for _ in query.any_of_themes)
            clauses.append(f"({anys})")
            for theme in query.any_of_themes:
                params.append(f"% {theme} %")
        for theme in query.excluded_themes:
            clauses.append("(' ' || themes || ' ') NOT LIKE ?")
            params.append(f"% {theme} %")
        if query.rating_min is not None:
            clauses.append("rating >= ?")
            params.append(int(query.rating_min))
        if query.rating_max is not None:
            clauses.append("rating <= ?")
            params.append(int(query.rating_max))
        if query.rating_deviation_max is not None:
            clauses.append("rating_dev <= ?")
            params.append(int(query.rating_deviation_max))
        if query.popularity_min is not None:
            clauses.append("popularity >= ?")
            params.append(int(query.popularity_min))
        if query.nb_plays_min is not None:
            clauses.append("nb_plays >= ?")
            params.append(int(query.nb_plays_min))
        if query.phase:
            clauses.append("phase = ?")
            params.append(query.phase)
        if query.solution_plies_min is not None:
            clauses.append("solution_plies >= ?")
            params.append(int(query.solution_plies_min))
        if query.solution_plies_max is not None:
            clauses.append("solution_plies <= ?")
            params.append(int(query.solution_plies_max))
        if query.mate_in is not None:
            tag = f"mateIn{int(query.mate_in)}"
            clauses.append("(' ' || themes || ' ') LIKE ?")
            params.append(f"% {tag} %")
        if query.opening_tag:
            clauses.append("opening_tags LIKE ?")
            params.append(f"%{query.opening_tag}%")
        if query.side_to_move in ("white", "black"):
            # Field 2 of FEN is the side-to-move letter.
            letter = "w" if query.side_to_move == "white" else "b"
            clauses.append("substr(fen, instr(fen, ' ') + 1, 1) = ?")
            params.append(letter)
        where = " AND ".join(clauses) if clauses else "1 = 1"
        return where, params

    def preview(self, query: SearchQuery, *, sample_size: int = 10) -> SearchPreview:
        where, params = self._where(query)
        with self._connect() as connection:
            self._create_schema(connection)
            count = connection.execute(
                f"SELECT COUNT(*) FROM puzzles WHERE {where}",
                params,
            ).fetchone()[0]
            sample_rows = connection.execute(
                f"SELECT id, fen, rating, themes, opening_tags, solution_plies "
                f"FROM puzzles WHERE {where} ORDER BY rating ASC LIMIT ?",
                (*params, sample_size),
            ).fetchall()
            hist_rows = connection.execute(
                f"SELECT MIN(rating), MAX(rating) FROM puzzles WHERE {where}",
                params,
            ).fetchone()
        preview = SearchPreview(count=count)
        for row in sample_rows:
            preview.sample.append(
                {
                    "id": row["id"],
                    "fen": row["fen"],
                    "rating": row["rating"],
                    "themes": row["themes"].split(),
                    "opening_tags": row["opening_tags"].split() if row["opening_tags"] else [],
                    "solution_plies": row["solution_plies"],
                }
            )
        preview.rating_histogram = self._histogram(where, params, hist_rows)
        return preview

    def _histogram(
        self,
        where: str,
        params: list[Any],
        bounds: sqlite3.Row | None,
    ) -> list[int]:
        buckets = [0] * 10
        if bounds is None or bounds[0] is None or bounds[1] is None:
            return buckets
        lo, hi = int(bounds[0]), int(bounds[1])
        if hi <= lo:
            hi = lo + 1
        step = (hi - lo) / 10.0
        with self._connect() as connection:
            for i in range(10):
                b_lo = lo + step * i
                b_hi = hi if i == 9 else lo + step * (i + 1)
                row = connection.execute(
                    f"SELECT COUNT(*) FROM puzzles WHERE {where} "
                    f"AND rating >= ? AND rating {'<=' if i == 9 else '<'} ?",
                    (*params, b_lo, b_hi),
                ).fetchone()
                buckets[i] = int(row[0])
        return buckets

    def opening_tags(self) -> list[str]:
        """Return the sorted, distinct list of opening tags in the index.

        Cached after the first call. Each puzzle can carry multiple
        space-separated tags in the OpeningTags column — this method splits
        and de-duplicates across all rows.
        """
        if self._opening_tags_cache is not None:
            return self._opening_tags_cache
        tags: set[str] = set()
        with self._connect() as connection:
            self._create_schema(connection)
            for row in connection.execute(
                "SELECT opening_tags FROM puzzles WHERE opening_tags != ''"
            ):
                for tag in row[0].split():
                    if tag:
                        tags.add(tag)
        self._opening_tags_cache = sorted(tags)
        return self._opening_tags_cache

    def matching_ids_ranked(self, query: SearchQuery, *, limit: int) -> list[dict[str, Any]]:
        """Return up to `limit` puzzles ordered by deterministic hash-rank."""
        from .curation import hash_rank

        where, params = self._where(query)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id, fen, moves, rating, themes, game_url FROM puzzles WHERE {where}",
                params,
            ).fetchall()
        ranked = sorted(
            (dict(row) | {"rank": hash_rank(query.seed, row["id"])} for row in rows),
            key=lambda item: item["rank"],
        )
        return ranked[:limit]
