"""Application service for puzzle presentation and authoritative submissions."""

from __future__ import annotations

import contextlib
import os
import secrets
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import chess
import chess.engine

from .catalog import RULES_VERSION, CatalogError, PuzzleCatalog
from .domain import Color, DomainError, Scope, compare, normalize_squares, resolve_scope
from .repository import SCHEMA_VERSION, ProgressRepository, RepositoryError


class ApplicationError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, status: int = 400, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class Presentation:
    puzzle_id: str
    created_at: float


class PresentationStore:
    """Process-local, expiring opaque presentation identifiers."""

    def __init__(self, *, ttl_seconds: int = 7200, clock: Callable[[], float] = time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._presentations: dict[str, Presentation] = {}

    def create(self, puzzle_id: str) -> str:
        now = self.clock()
        self._purge(now)
        identifier = secrets.token_urlsafe(24)
        self._presentations[identifier] = Presentation(puzzle_id, now)
        return identifier

    def resolve(self, identifier: str) -> str:
        now = self.clock()
        presentation = self._presentations.get(identifier)
        if presentation is None or now - presentation.created_at > self.ttl_seconds:
            self._presentations.pop(identifier, None)
            raise ApplicationError(
                "stale_presentation", "Puzzle presentation is invalid or stale", status=404
            )
        return presentation.puzzle_id

    def _purge(self, now: float) -> None:
        stale = [
            identifier
            for identifier, value in self._presentations.items()
            if now - value.created_at > self.ttl_seconds
        ]
        for identifier in stale:
            del self._presentations[identifier]


class TrainingService:
    def __init__(
        self,
        catalog: PuzzleCatalog,
        repository: ProgressRepository,
        presentations: PresentationStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.catalog = catalog
        self.repository = repository
        self.presentations = presentations
        self.now = now

    def next_puzzle(self, previous_id: str | None = None) -> dict[str, Any]:
        puzzle = self.catalog.next(previous_id)
        public = puzzle.public_dict()
        public["presentation_id"] = self.presentations.create(puzzle.puzzle_id)
        return public

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApplicationError("invalid_request", "JSON object required")
        attempt_id = payload.get("attempt_id")
        presentation_id = payload.get("presentation_id")
        if not isinstance(attempt_id, str) or not 8 <= len(attempt_id) <= 128:
            raise ApplicationError("invalid_attempt_id", "Attempt ID must be 8-128 characters")
        try:
            existing = self.repository.get_attempt(attempt_id)
            if existing is not None:
                return self._result(existing, self.repository.stats(), replayed=True)
        except RepositoryError as exc:
            raise ApplicationError(
                "persistence_failure",
                "Progress could not be read; your answer is still editable",
                status=500,
                retryable=True,
            ) from exc
        if not isinstance(presentation_id, str):
            raise ApplicationError("invalid_presentation", "Presentation ID is required")
        try:
            scope = Scope(payload.get("scope"))
            submitted_hanging = normalize_squares(payload.get("hanging", []))
        except (ValueError, TypeError, DomainError) as exc:
            raise ApplicationError(
                "invalid_selection", "Scope or selected squares are invalid"
            ) from exc
        completion_ms = payload.get("completion_ms", 0)
        if (
            not isinstance(completion_ms, int)
            or isinstance(completion_ms, bool)
            or not 0 <= completion_ms <= 86_400_000
        ):
            raise ApplicationError("invalid_duration", "Completion duration is out of bounds")
        puzzle_id = self.presentations.resolve(presentation_id)
        try:
            puzzle = self.catalog.get(puzzle_id)
            expected = self.catalog.expected(puzzle_id, scope)
        except CatalogError as exc:
            raise ApplicationError("catalog_error", "Puzzle is unavailable", status=409) from exc
        effective_colors = resolve_scope(scope, puzzle.side_to_move)
        self._validate_eligibility(
            puzzle.presented_fen,
            effective_colors,
            submitted_hanging,
        )
        feedback = {
            "hanging": compare(expected.hanging, submitted_hanging).to_dict(),
        }
        point = expected.hanging == submitted_hanging
        attempt = {
            "attempt_id": attempt_id,
            "puzzle_id": puzzle.puzzle_id,
            "presented_fen": puzzle.presented_fen,
            "scope": scope.value,
            "effective_colors": [color.value for color in effective_colors],
            # Retained in the storage schema for backwards compatibility. Every hanging piece is
            # necessarily undefended, so the single submitted set is safe to mirror here.
            "submitted_undefended": sorted(submitted_hanging),
            "submitted_hanging": sorted(submitted_hanging),
            "expected_undefended": sorted(expected.undefended),
            "expected_hanging": sorted(expected.hanging),
            "feedback": feedback,
            "correct": point,
            "point_awarded": point,
            "completion_ms": completion_ms,
            "submitted_at": self.now().isoformat(),
            "schema_version": SCHEMA_VERSION,
            "rules_version": RULES_VERSION,
        }
        try:
            committed, created = self.repository.commit_attempt(attempt)
            statistics = self.repository.stats()
        except RepositoryError as exc:
            raise ApplicationError(
                "persistence_failure",
                "Progress could not be saved; your answer is still editable",
                status=500,
                retryable=True,
            ) from exc
        return self._result(committed, statistics, replayed=not created)

    @staticmethod
    def _validate_eligibility(
        fen: str, effective_colors: tuple[Color, ...], squares: frozenset[str]
    ) -> None:
        board = chess.Board(fen)
        allowed = {color.chess_color for color in effective_colors}
        for square_name in squares:
            piece = board.piece_at(chess.parse_square(square_name))
            if piece is None or piece.piece_type == chess.KING or piece.color not in allowed:
                raise ApplicationError(
                    "ineligible_square", f"{square_name} is not eligible in this scope"
                )

    @staticmethod
    def _result(
        attempt: dict[str, Any], statistics: dict[str, Any], *, replayed: bool
    ) -> dict[str, Any]:
        return {
            "attempt_id": attempt["attempt_id"],
            "puzzle_id": attempt["puzzle_id"],
            "scope": attempt["scope"],
            "point_awarded": attempt["point_awarded"],
            "feedback": attempt["feedback"],
            "expected": {
                "hanging": attempt["expected_hanging"],
            },
            "statistics": statistics,
            "replayed": replayed,
        }


@dataclass(slots=True)
class SolveSession:
    puzzle_id: str
    board_fen: str
    remaining_moves: list[str]
    submitted_moves: list[str]
    wrong_moves: int
    created_at: float
    started_at: float
    starting_fen: str = ""


class SolveStore:
    """Process-local, expiring solve-mode session store."""

    def __init__(self, *, ttl_seconds: int = 7200, clock: Callable[[], float] = time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._sessions: dict[str, SolveSession] = {}

    def create(self, puzzle_id: str, board_fen: str, solution_moves: list[str]) -> str:
        now = self.clock()
        self._purge(now)
        identifier = secrets.token_urlsafe(24)
        self._sessions[identifier] = SolveSession(
            puzzle_id=puzzle_id,
            board_fen=board_fen,
            remaining_moves=list(solution_moves),
            submitted_moves=[],
            wrong_moves=0,
            created_at=now,
            started_at=now,
            starting_fen=board_fen,
        )
        return identifier

    def resolve(self, identifier: str) -> SolveSession:
        now = self.clock()
        session = self._sessions.get(identifier)
        if session is None or now - session.created_at > self.ttl_seconds:
            self._sessions.pop(identifier, None)
            raise ApplicationError("stale_session", "Solve session is invalid or stale", status=404)
        return session

    def drop(self, identifier: str) -> None:
        self._sessions.pop(identifier, None)

    def _purge(self, now: float) -> None:
        stale = [
            identifier
            for identifier, value in self._sessions.items()
            if now - value.created_at > self.ttl_seconds
        ]
        for identifier in stale:
            del self._sessions[identifier]


TACTICS_BATCH_SIZE = 5


@dataclass(frozen=True, slots=True)
class TacticsBatch:
    index: int
    puzzle_ids: tuple[str, ...]
    total_rating: int
    points_possible: int


def compute_batches(
    catalog: PuzzleCatalog, batch_size: int = TACTICS_BATCH_SIZE
) -> tuple[TacticsBatch, ...]:
    """LPT-balance the catalog into batches of `batch_size` by rating."""
    puzzles = [catalog.get(pid) for pid in catalog._ids]
    n = len(puzzles)
    if n == 0 or n % batch_size != 0:
        raise ValueError(f"catalog size {n} must be a multiple of {batch_size}")
    num_batches = n // batch_size
    bins: list[dict[str, Any]] = [{"puzzles": [], "total_rating": 0} for _ in range(num_batches)]
    # Descending by rating, ties broken by puzzle_id for determinism.
    for puzzle in sorted(puzzles, key=lambda p: (-(p.rating or 0), p.puzzle_id)):
        # Bins under capacity, sorted so the lightest bin comes first.
        eligible = [b for b in bins if len(b["puzzles"]) < batch_size]
        chosen = min(eligible, key=lambda b: (b["total_rating"], len(b["puzzles"])))
        chosen["puzzles"].append(puzzle)
        chosen["total_rating"] += puzzle.rating or 0
    result: list[TacticsBatch] = []
    for index, bucket in enumerate(bins):
        # Sort puzzles within a batch by rating ascending — warm-up first.
        ordered = sorted(bucket["puzzles"], key=lambda p: (p.rating or 0, p.puzzle_id))
        points_possible = sum(_score_for_puzzle(p.rating or 0, 0) for p in ordered)
        result.append(
            TacticsBatch(
                index=index,
                puzzle_ids=tuple(p.puzzle_id for p in ordered),
                total_rating=bucket["total_rating"],
                points_possible=points_possible,
            )
        )
    return tuple(result)


def _uci_line_to_san(fen: str, uci_moves: tuple[str, ...] | list[str]) -> list[str]:
    """Convert a sequence of UCI moves against a starting FEN into SAN strings."""
    san, _ = _replay_solution(fen, uci_moves)
    return san


def _replay_solution(
    fen: str, uci_moves: tuple[str, ...] | list[str]
) -> tuple[list[str], list[str]]:
    """Return (san_list, fen_sequence) for a solution line. fen_sequence is
    [starting_fen, fen_after_move_1, fen_after_move_2, ...]."""
    board = chess.Board(fen)
    san: list[str] = []
    fens: list[str] = [board.fen()]
    for uci in uci_moves:
        try:
            move = chess.Move.from_uci(uci)
        except (ValueError, chess.InvalidMoveError):
            break
        if move not in board.legal_moves:
            break
        san.append(board.san(move))
        board.push(move)
        fens.append(board.fen())
    return san, fens


def _fen_start_metadata(fen: str) -> dict[str, Any]:
    """Return `starting_fullmove` and `starting_turn` derived from a FEN."""
    board = chess.Board(fen)
    return {
        "starting_fullmove": board.fullmove_number,
        "starting_turn": "white" if board.turn == chess.WHITE else "black",
    }


def _score_for_puzzle(rating: int, wrong_moves: int) -> int:
    """Points earned for a puzzle given its rating and how many wrong moves were made."""
    full = round((rating or 0) / 100)
    if wrong_moves == 0:
        return full
    if wrong_moves == 1:
        return round((rating or 0) / 200)
    return 0


class TacticsService:
    """Serves the tactics catalog with Lichess-style solve-mode move validation."""

    def __init__(
        self,
        catalog: PuzzleCatalog,
        repository: ProgressRepository,
        sessions: SolveStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        batches: tuple[TacticsBatch, ...] | None = None,
        package: str | None = None,
    ) -> None:
        self.catalog = catalog
        self.repository = repository
        self.sessions = sessions
        self.now = now
        self.batches = batches if batches is not None else compute_batches(catalog)
        self.batches_per_cycle = len(self.batches)
        self.package = package or catalog.slug

    def _current_context(self) -> tuple[int, TacticsBatch, dict[str, int]]:
        """Return (cycle, current_batch, attempted_by_id) for the active batch."""
        cycle = self.repository.current_cycle(self.batches_per_cycle, package=self.package)
        done = self.repository.completed_batches(cycle, package=self.package)
        for batch in self.batches:
            if batch.index in done:
                continue
            attempts = self.repository.solve_attempts_in_batch(
                batch.index, cycle, package=self.package
            )
            attempted = {row["puzzle_id"]: int(row["wrong_moves"]) for row in attempts}
            return cycle, batch, attempted
        # Shouldn't get here — current_cycle() rolls forward once a cycle is done.
        return cycle, self.batches[0], {}

    def _batch_view(
        self, cycle: int, batch: TacticsBatch, attempted: dict[str, int]
    ) -> dict[str, Any]:
        earned = sum(
            _score_for_puzzle(self.catalog.get(pid).rating or 0, wrong)
            for pid, wrong in attempted.items()
        )
        position = len(attempted) + 1
        return {
            "index": batch.index,
            "total_batches": self.batches_per_cycle,
            "position": min(position, TACTICS_BATCH_SIZE),
            "batch_size": TACTICS_BATCH_SIZE,
            "puzzles_played": len(attempted),
            "points_earned": earned,
            "points_possible": batch.points_possible,
            "cycle": cycle,
        }

    def next_puzzle(self, previous_id: str | None = None) -> dict[str, Any]:
        cycle, batch, attempted = self._current_context()
        remaining = [pid for pid in batch.puzzle_ids if pid not in attempted]
        if not remaining:
            # Defensive: batch is full but wasn't marked complete. Just pick any.
            remaining = list(batch.puzzle_ids)
        puzzle_id = remaining[0]
        if previous_id and previous_id == puzzle_id and len(remaining) > 1:
            puzzle_id = remaining[1]
        puzzle = self.catalog.get(puzzle_id)
        if not puzzle.solution_moves_uci:
            raise ApplicationError("catalog_error", "Puzzle is missing solution moves", status=500)
        session_id = self.sessions.create(
            puzzle.puzzle_id, puzzle.presented_fen, list(puzzle.solution_moves_uci)
        )
        public = puzzle.public_dict()
        public["session_id"] = session_id
        public["legal_targets"] = _legal_targets(puzzle.presented_fen)
        public["remaining_plies"] = len(puzzle.solution_moves_uci)
        public["batch"] = self._batch_view(cycle, batch, attempted)
        public["batch"]["full_points"] = _score_for_puzzle(puzzle.rating or 0, 0)
        public.update(_fen_start_metadata(puzzle.presented_fen))
        return public

    def submit_move(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApplicationError("invalid_request", "JSON object required")
        session_id = payload.get("session_id")
        uci = payload.get("uci")
        if not isinstance(session_id, str) or not isinstance(uci, str):
            raise ApplicationError("invalid_move", "session_id and uci are required strings")
        session = self.sessions.resolve(session_id)
        if not session.remaining_moves:
            raise ApplicationError(
                "already_completed", "This puzzle has already been solved", status=409
            )
        try:
            board = chess.Board(session.board_fen)
        except ValueError as exc:
            raise ApplicationError(
                "invalid_session_state", "Session board is corrupt", status=500
            ) from exc
        try:
            move = chess.Move.from_uci(uci)
        except (ValueError, chess.InvalidMoveError) as exc:
            raise ApplicationError("illegal_move", "Not a valid move notation") from exc
        if move not in board.legal_moves:
            return {
                "correct": False,
                "reason": "illegal",
                "retry": True,
                "wrong_moves": session.wrong_moves,
            }
        expected_uci = session.remaining_moves[0]
        if uci != expected_uci:
            session.wrong_moves += 1
            return {
                "correct": False,
                "reason": "wrong_move",
                "retry": True,
                "wrong_moves": session.wrong_moves,
            }
        user_san = board.san(move)
        session.submitted_moves.append(uci)
        session.remaining_moves.pop(0)
        board.push(move)
        fen_after_user = board.fen()
        opponent_uci: str | None = None
        opponent_san: str | None = None
        fen_after_opponent: str | None = None
        if session.remaining_moves:
            opponent_uci = session.remaining_moves.pop(0)
            try:
                opponent_move = chess.Move.from_uci(opponent_uci)
            except (ValueError, chess.InvalidMoveError) as exc:
                raise ApplicationError(
                    "invalid_solution", "Solution contained an invalid opponent move", status=500
                ) from exc
            if opponent_move not in board.legal_moves:
                raise ApplicationError(
                    "invalid_solution",
                    "Solution's opponent move is illegal from this position",
                    status=500,
                )
            opponent_san = board.san(opponent_move)
            board.push(opponent_move)
            fen_after_opponent = board.fen()
            session.submitted_moves.append(opponent_uci)
        session.board_fen = board.fen()
        completed = not session.remaining_moves
        response: dict[str, Any] = {
            "correct": True,
            "user_move": uci,
            "user_san": user_san,
            "fen_after_user": fen_after_user,
            "opponent_move": opponent_uci,
            "opponent_san": opponent_san,
            "fen_after_opponent": fen_after_opponent,
            "presented_fen": session.board_fen,
            "legal_targets": _legal_targets(session.board_fen) if not completed else {},
            "completed": completed,
            "wrong_moves": session.wrong_moves,
        }
        if completed:
            self._finalize_completion(session_id, session, response, given_up=False)
        return response

    def reveal(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Give up: commit a 0-point attempt and return the full solution for review."""
        if not isinstance(payload, dict):
            raise ApplicationError("invalid_request", "JSON object required")
        session_id = payload.get("session_id")
        if not isinstance(session_id, str):
            raise ApplicationError("invalid_move", "session_id is required")
        session = self.sessions.resolve(session_id)
        try:
            puzzle = self.catalog.get(session.puzzle_id)
        except CatalogError as exc:
            raise ApplicationError(
                "catalog_error", "Puzzle vanished mid-session", status=409
            ) from exc
        response: dict[str, Any] = {
            "correct": False,
            "presented_fen": puzzle.presented_fen,
            "legal_targets": {},
            "completed": True,
            "given_up": True,
            "wrong_moves": session.wrong_moves,
        }
        # Mark the session as given-up by inflating wrong_moves so it scores 0
        # (matches the "2+ mistakes" rule).
        session.wrong_moves = max(session.wrong_moves, 2)
        self._finalize_completion(session_id, session, response, given_up=True)
        return response

    def _finalize_completion(
        self,
        session_id: str,
        session: SolveSession,
        response: dict[str, Any],
        *,
        given_up: bool,
    ) -> None:
        try:
            puzzle = self.catalog.get(session.puzzle_id)
        except CatalogError as exc:
            raise ApplicationError(
                "catalog_error", "Puzzle vanished mid-session", status=409
            ) from exc
        cycle, batch, attempted = self._current_context()
        puzzle_points = _score_for_puzzle(puzzle.rating or 0, session.wrong_moves)
        point = session.wrong_moves == 0 and not given_up
        completion_ms = int((self.sessions.clock() - session.started_at) * 1000)
        attempt = {
            "attempt_id": secrets.token_urlsafe(16),
            "puzzle_id": puzzle.puzzle_id,
            "presented_fen": puzzle.presented_fen,
            "submitted_moves": list(session.submitted_moves),
            "expected_moves": list(puzzle.solution_moves_uci),
            "wrong_moves": session.wrong_moves,
            "completed": True,
            "point_awarded": point,
            "completion_ms": completion_ms,
            "submitted_at": self.now().isoformat(),
            "schema_version": SCHEMA_VERSION,
            "rules_version": RULES_VERSION,
            "batch_index": batch.index,
            "cycle": cycle,
            "package": self.package,
        }
        batch_result: dict[str, Any] | None = None
        try:
            self.repository.commit_solve_attempt(attempt)
            attempted = {
                row["puzzle_id"]: int(row["wrong_moves"])
                for row in self.repository.solve_attempts_in_batch(
                    batch.index, cycle, package=self.package
                )
            }
            if len(attempted) >= TACTICS_BATCH_SIZE and set(attempted).issuperset(batch.puzzle_ids):
                per_puzzle = [
                    _score_for_puzzle(self.catalog.get(pid).rating or 0, attempted[pid])
                    for pid in batch.puzzle_ids
                ]
                batch_row = {
                    "batch_index": batch.index,
                    "cycle": cycle,
                    "completed_at": self.now().isoformat(),
                    "points_earned": sum(per_puzzle),
                    "points_possible": batch.points_possible,
                    "puzzles_solved": sum(1 for p in per_puzzle if p > 0),
                    "puzzle_ids": list(batch.puzzle_ids),
                    "per_puzzle_points": per_puzzle,
                    "schema_version": SCHEMA_VERSION,
                    "rules_version": RULES_VERSION,
                    "package": self.package,
                }
                self.repository.commit_tactics_batch(batch_row)
                batch_result = {
                    "index": batch.index,
                    "cycle": cycle,
                    "points_earned": sum(per_puzzle),
                    "points_possible": batch.points_possible,
                    "per_puzzle_points": per_puzzle,
                    "puzzle_ids": list(batch.puzzle_ids),
                }
            statistics = self.repository.solve_stats(package=self.package)
            batch_stats = self.repository.tactics_batch_stats(package=self.package)
        except RepositoryError as exc:
            raise ApplicationError(
                "persistence_failure",
                "Progress could not be saved",
                status=500,
                retryable=True,
            ) from exc
        san, fen_sequence = _replay_solution(puzzle.presented_fen, puzzle.solution_moves_uci)
        starting_board = chess.Board(puzzle.presented_fen)
        response["point_awarded"] = point
        response["puzzle_points"] = puzzle_points
        response["given_up"] = given_up
        response["statistics"] = statistics
        response["batch_statistics"] = batch_stats
        response["expected_moves"] = list(puzzle.solution_moves_uci)
        response["expected_moves_san"] = san
        response["fen_sequence"] = fen_sequence
        response["starting_fullmove"] = starting_board.fullmove_number
        response["starting_turn"] = "white" if starting_board.turn == chess.WHITE else "black"
        response["rating"] = puzzle.rating
        response["batch"] = self._batch_view(cycle, batch, attempted)
        response["batch"]["full_points"] = _score_for_puzzle(puzzle.rating or 0, 0)
        response["batch_completed"] = batch_result is not None
        response["batch_result"] = batch_result
        self.sessions.drop(session_id)


class PreviewBatchStore:
    """Process-local, expiring store of Lichess puzzle-row batches used by
    the search builder's "Try these 10" flow. Each entry holds the puzzle
    rows sampled from a SearchQuery so the play page can iterate through
    them without re-hitting the index."""

    def __init__(self, *, ttl_seconds: int = 7200, clock: Callable[[], float] = time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._batches: dict[str, tuple[list[dict[str, Any]], float]] = {}

    def create(self, puzzle_rows: list[dict[str, Any]]) -> str:
        now = self.clock()
        self._purge(now)
        identifier = secrets.token_urlsafe(24)
        self._batches[identifier] = (list(puzzle_rows), now)
        return identifier

    def resolve(self, identifier: str) -> list[dict[str, Any]]:
        now = self.clock()
        entry = self._batches.get(identifier)
        if entry is None or now - entry[1] > self.ttl_seconds:
            self._batches.pop(identifier, None)
            raise ApplicationError("stale_batch", "Preview batch is invalid or stale", status=404)
        return entry[0]

    def _purge(self, now: float) -> None:
        stale = [
            identifier
            for identifier, (_, created) in self._batches.items()
            if now - created > self.ttl_seconds
        ]
        for identifier in stale:
            del self._batches[identifier]


class TacticsPreviewService:
    """Stateless preview: play a Lichess puzzle without touching the DB.

    Used by the search builder so the user can try a couple of puzzles before
    saving them as a package. No batches, no scoring, no persistence — sessions
    are held in an in-memory SolveStore for their TTL.
    """

    def __init__(self, sessions: SolveStore) -> None:
        self.sessions = sessions

    def start(self, puzzle_row: dict[str, Any]) -> dict[str, Any]:
        moves = str(puzzle_row.get("moves", "")).split()
        if not moves:
            raise ApplicationError("invalid_puzzle", "puzzle has no moves", status=400)
        try:
            board = chess.Board(str(puzzle_row["fen"]))
            first = chess.Move.from_uci(moves[0])
            if first not in board.legal_moves:
                raise ApplicationError(
                    "invalid_puzzle", "first move is not legal from source FEN", status=400
                )
            board.push(first)
        except (KeyError, ValueError, chess.InvalidMoveError) as exc:
            raise ApplicationError(
                "invalid_puzzle", f"cannot start puzzle: {exc}", status=400
            ) from exc
        presented_fen = board.fen()
        solution = moves[1:]
        puzzle_id = str(puzzle_row.get("id") or puzzle_row.get("puzzle_id") or "preview")
        session_id = self.sessions.create(puzzle_id, presented_fen, solution)
        response = {
            "session_id": session_id,
            "puzzle_id": puzzle_id,
            "presented_fen": presented_fen,
            "side_to_move": "white" if board.turn == chess.WHITE else "black",
            "rating": puzzle_row.get("rating"),
            "themes": puzzle_row.get("themes") or [],
            "source_url": puzzle_row.get("game_url") or f"https://lichess.org/training/{puzzle_id}",
            "legal_targets": _legal_targets(presented_fen),
            "remaining_plies": len(solution),
        }
        response.update(_fen_start_metadata(presented_fen))
        return response

    def submit_move(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApplicationError("invalid_request", "JSON object required")
        session_id = payload.get("session_id")
        uci = payload.get("uci")
        if not isinstance(session_id, str) or not isinstance(uci, str):
            raise ApplicationError("invalid_move", "session_id and uci are required strings")
        session = self.sessions.resolve(session_id)
        if not session.remaining_moves:
            raise ApplicationError(
                "already_completed", "This puzzle has already been solved", status=409
            )
        try:
            board = chess.Board(session.board_fen)
        except ValueError as exc:
            raise ApplicationError(
                "invalid_session_state", "Session board is corrupt", status=500
            ) from exc
        try:
            move = chess.Move.from_uci(uci)
        except (ValueError, chess.InvalidMoveError) as exc:
            raise ApplicationError("illegal_move", "Not a valid move notation") from exc
        if move not in board.legal_moves:
            return {
                "correct": False,
                "reason": "illegal",
                "retry": True,
                "wrong_moves": session.wrong_moves,
            }
        expected_uci = session.remaining_moves[0]
        if uci != expected_uci:
            session.wrong_moves += 1
            return {
                "correct": False,
                "reason": "wrong_move",
                "retry": True,
                "wrong_moves": session.wrong_moves,
            }
        user_san = board.san(move)
        session.submitted_moves.append(uci)
        session.remaining_moves.pop(0)
        board.push(move)
        fen_after_user = board.fen()
        opponent_uci: str | None = None
        opponent_san: str | None = None
        fen_after_opponent: str | None = None
        if session.remaining_moves:
            opponent_uci = session.remaining_moves.pop(0)
            try:
                opponent_move = chess.Move.from_uci(opponent_uci)
            except (ValueError, chess.InvalidMoveError) as exc:
                raise ApplicationError(
                    "invalid_solution", "Solution's opponent move is invalid", status=500
                ) from exc
            if opponent_move not in board.legal_moves:
                raise ApplicationError(
                    "invalid_solution",
                    "Solution's opponent move is illegal from this position",
                    status=500,
                )
            opponent_san = board.san(opponent_move)
            board.push(opponent_move)
            fen_after_opponent = board.fen()
            session.submitted_moves.append(opponent_uci)
        session.board_fen = board.fen()
        completed = not session.remaining_moves
        response: dict[str, Any] = {
            "correct": True,
            "user_move": uci,
            "user_san": user_san,
            "fen_after_user": fen_after_user,
            "opponent_move": opponent_uci,
            "opponent_san": opponent_san,
            "fen_after_opponent": fen_after_opponent,
            "presented_fen": session.board_fen,
            "legal_targets": _legal_targets(session.board_fen) if not completed else {},
            "completed": completed,
            "wrong_moves": session.wrong_moves,
        }
        if completed:
            self.sessions.drop(session_id)
        return response

    def reveal(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApplicationError("invalid_request", "JSON object required")
        session_id = payload.get("session_id")
        if not isinstance(session_id, str):
            raise ApplicationError("invalid_move", "session_id is required")
        session = self.sessions.resolve(session_id)
        full_moves = list(session.submitted_moves) + list(session.remaining_moves)
        starting_fen = session.starting_fen or session.board_fen
        san, fen_sequence = _replay_solution(starting_fen, full_moves)
        self.sessions.drop(session_id)
        return {
            "correct": False,
            "completed": True,
            "given_up": True,
            "presented_fen": starting_fen,
            "legal_targets": {},
            "expected_moves": full_moves,
            "expected_moves_san": san,
            "fen_sequence": fen_sequence,
            "wrong_moves": session.wrong_moves,
        }


def _legal_targets(fen: str) -> dict[str, list[dict[str, str | None]]]:
    """Return a mapping from-square → list of {to, promotion} for all legal moves."""
    board = chess.Board(fen)
    result: dict[str, list[dict[str, str | None]]] = {}
    for move in board.legal_moves:
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        promotion = chess.piece_symbol(move.promotion) if move.promotion else None
        result.setdefault(from_sq, []).append({"to": to_sq, "promotion": promotion})
    return result


# ─── Pawn War: engine wrapper, session store, service ──────────────────────


@contextlib.contextmanager
def _daemon_default_threads():
    """Temporarily force new threading.Thread instances to be daemon.

    python-chess spawns a non-daemon background thread inside popen_uci; that
    thread would otherwise block interpreter shutdown until we can signal the
    subprocess. Making it daemon lets Python exit cleanly after we SIGKILL
    the Stockfish process in EngineHost.shutdown().
    """
    original_init = threading.Thread.__init__

    def daemon_init(self, *args, **kwargs):
        kwargs["daemon"] = True
        original_init(self, *args, **kwargs)

    threading.Thread.__init__ = daemon_init
    try:
        yield
    finally:
        threading.Thread.__init__ = original_init


def _apply_strength(engine: Any, elo: int) -> chess.engine.Limit:
    """Configure the engine to play at approximately the requested Elo.

    Stockfish's native UCI_Elo bottoms out at ~1320. For anything lower we
    disable UCI_LimitStrength and pin down strength via Skill Level plus a
    hard depth cap. Returns the search Limit to use for the next move.
    """
    if elo >= PAWN_NATIVE_ELO_FLOOR:
        with contextlib.suppress(chess.engine.EngineError):
            engine.configure(
                {
                    "UCI_LimitStrength": True,
                    "UCI_Elo": int(elo),
                    "Skill Level": 20,
                }
            )
        return chess.engine.Limit(time=PAWN_MOVETIME_S)

    # Sub-native range: Skill Level + depth cap gives a beatable engine.
    # Table is intentionally coarse; playing strength below 1200 is not linear.
    if elo < 700:
        skill, depth = 0, 1
    elif elo < 900:
        skill, depth = 2, 2
    elif elo < 1100:
        skill, depth = 5, 3
    else:  # 1100..1319
        skill, depth = 10, 5
    with contextlib.suppress(chess.engine.EngineError):
        engine.configure({"UCI_LimitStrength": False, "Skill Level": skill})
    return chess.engine.Limit(time=PAWN_MOVETIME_S, depth=depth)


PAWN_KINGLESS_FEN = "7k/pppppppp/8/8/8/8/PPPPPPPP/K7 w - - 0 1"
PAWN_KINGS_FEN = "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 w - - 0 1"
PAWN_VARIANTS = ("kingless", "with_kings")
PAWN_ELO_MIN = 400
PAWN_ELO_MAX = 2850
PAWN_NATIVE_ELO_FLOOR = 1320  # Stockfish's own UCI_Elo minimum; below this we drive
#                                strength through Skill Level + depth cap.
PAWN_MOVETIME_S = 0.5


class EngineHost:
    """Lazy-spawned Stockfish subprocess, reused across pawn-war games."""

    def __init__(self, path: str | None) -> None:
        self.path = path
        self._engine: Any = None  # chess.engine.SimpleEngine when spawned
        self._error: str | None = None if path else "stockfish path not configured"

    def available(self) -> bool:
        return self.path is not None and self._error is None

    def status(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "state": "spawned"
            if self._engine is not None
            else ("ready" if self.available() else "unavailable"),
            "error": self._error,
        }

    def _ensure(self) -> Any:
        if self._engine is not None:
            return self._engine
        if self.path is None:
            raise ApplicationError(
                "engine_unavailable",
                "Stockfish is not configured on this server",
                status=503,
                retryable=False,
            )
        # python-chess spawns a non-daemon background thread that would keep
        # the process alive after main exit. Force it to daemon so Python can
        # exit cleanly; on shutdown we SIGKILL the subprocess directly.
        with _daemon_default_threads():
            try:
                self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
            except (OSError, chess.engine.EngineError) as exc:
                self._error = f"could not spawn engine: {exc}"
                raise ApplicationError(
                    "engine_unavailable",
                    "Stockfish could not be launched",
                    status=503,
                    retryable=False,
                ) from exc
        return self._engine

    def new_game(self) -> None:
        # python-chess's SimpleEngine doesn't expose ucinewgame; engine.play()
        # against a fresh board is sufficient to start a new game.
        return

    def choose(
        self, board: chess.Board, *, elo: int, root_moves: list[chess.Move] | None = None
    ) -> chess.Move:
        engine = self._ensure()
        limit = _apply_strength(engine, elo)
        try:
            result = engine.play(board, limit, root_moves=root_moves)
        except chess.engine.EngineError as exc:
            raise ApplicationError(
                "engine_failed", "Stockfish did not produce a move", status=502
            ) from exc
        if result.move is None:
            raise ApplicationError("engine_no_move", "Stockfish returned no move", status=502)
        return result.move

    def shutdown(self) -> None:
        engine = self._engine
        self._engine = None
        if engine is None:
            return
        # Grab the subprocess PID before any cleanup, so we can force-kill if quit hangs.
        pid: int | None = None
        with contextlib.suppress(Exception):
            pid = engine.transport.get_pid()
        # Some Stockfish builds ignore the UCI 'quit' command; use SIGKILL directly.
        if pid is not None:
            with contextlib.suppress(OSError, ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


@dataclass(slots=True)
class PawnSession:
    game_id: str
    variant: str
    elo: int
    human_color: chess.Color
    board_fen: str
    created_at: float
    game_over: bool = False
    result: str | None = None
    result_reason: str | None = None


class PawnSessionStore:
    """Process-local expiring pawn-game sessions."""

    def __init__(self, *, ttl_seconds: int = 7200, clock: Callable[[], float] = time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._sessions: dict[str, PawnSession] = {}

    def create(self, variant: str, elo: int, human_color: chess.Color, board_fen: str) -> str:
        now = self.clock()
        self._purge(now)
        identifier = secrets.token_urlsafe(24)
        self._sessions[identifier] = PawnSession(
            game_id=identifier,
            variant=variant,
            elo=elo,
            human_color=human_color,
            board_fen=board_fen,
            created_at=now,
        )
        return identifier

    def resolve(self, identifier: str) -> PawnSession:
        now = self.clock()
        session = self._sessions.get(identifier)
        if session is None or now - session.created_at > self.ttl_seconds:
            self._sessions.pop(identifier, None)
            raise ApplicationError(
                "stale_session", "Pawn-war session is invalid or stale", status=404
            )
        return session

    def drop(self, identifier: str) -> None:
        self._sessions.pop(identifier, None)

    def _purge(self, now: float) -> None:
        stale = [
            identifier
            for identifier, value in self._sessions.items()
            if now - value.created_at > self.ttl_seconds
        ]
        for identifier in stale:
            del self._sessions[identifier]


class PawnGameService:
    """Serves the pawn-war mini-game against Stockfish (kingless or with kings)."""

    def __init__(self, engine: EngineHost, sessions: PawnSessionStore) -> None:
        self.engine = engine
        self.sessions = sessions

    def new_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApplicationError("invalid_request", "JSON object required")
        variant = payload.get("variant", "kingless")
        if variant not in PAWN_VARIANTS:
            raise ApplicationError("invalid_variant", "variant must be kingless or with_kings")
        elo = payload.get("elo", 1500)
        if not isinstance(elo, int) or isinstance(elo, bool):
            raise ApplicationError("invalid_elo", "elo must be an integer")
        if not PAWN_ELO_MIN <= elo <= PAWN_ELO_MAX:
            raise ApplicationError(
                "invalid_elo", f"elo must be between {PAWN_ELO_MIN} and {PAWN_ELO_MAX}"
            )
        side = payload.get("side", "white")
        if side == "random":
            human_color = chess.WHITE if secrets.randbits(1) else chess.BLACK
        elif side == "white":
            human_color = chess.WHITE
        elif side == "black":
            human_color = chess.BLACK
        else:
            raise ApplicationError("invalid_side", "side must be white, black, or random")

        board_fen = PAWN_KINGLESS_FEN if variant == "kingless" else PAWN_KINGS_FEN
        self.engine.new_game()
        game_id = self.sessions.create(variant, elo, human_color, board_fen)

        session = self.sessions.resolve(game_id)
        board = chess.Board(board_fen)
        starting_fen = board.fen()
        engine_move_uci: str | None = None
        engine_san: str | None = None
        # If the engine plays white (human chose black), have Stockfish move first.
        if board.turn != human_color:
            move = self._engine_play(board, variant, elo)
            engine_san = board.san(move)
            board.push(move)
            session.board_fen = board.fen()
            engine_move_uci = move.uci()
        snapshot = self._snapshot(session, board)
        public = self._public(snapshot)
        public["engine_move"] = engine_move_uci
        public["engine_san"] = engine_san
        public["user_move"] = None
        public["user_san"] = None
        public["starting_fen"] = starting_fen
        public.update(_fen_start_metadata(starting_fen))
        return public

    def submit_move(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApplicationError("invalid_request", "JSON object required")
        game_id = payload.get("game_id")
        uci = payload.get("uci")
        if not isinstance(game_id, str) or not isinstance(uci, str):
            raise ApplicationError("invalid_move", "game_id and uci are required strings")
        session = self.sessions.resolve(game_id)
        if session.game_over:
            raise ApplicationError("already_over", "Game already ended", status=409)
        board = chess.Board(session.board_fen)
        if board.turn != session.human_color:
            raise ApplicationError("not_your_turn", "It is not your turn", status=409)
        try:
            move = chess.Move.from_uci(uci)
        except (ValueError, chess.InvalidMoveError) as exc:
            raise ApplicationError("illegal_move", "Not a valid move notation") from exc
        allowed = _pawn_legal_moves(board, session.variant)
        if move not in allowed:
            return {
                "correct": False,
                "reason": "illegal",
                "retry": True,
                **self._public(self._snapshot(session, board)),
            }
        user_san = board.san(move)
        board.push(move)
        fen_after_user = board.fen()
        session.board_fen = fen_after_user
        response = self._snapshot(session, board)
        engine_move_uci: str | None = None
        engine_san: str | None = None
        fen_after_engine: str | None = None
        if not response["game_over"] and board.turn != session.human_color:
            engine_move = self._engine_play(board, session.variant, session.elo)
            engine_san = board.san(engine_move)
            board.push(engine_move)
            fen_after_engine = board.fen()
            session.board_fen = fen_after_engine
            engine_move_uci = engine_move.uci()
            response = self._snapshot(session, board)
        if response["game_over"]:
            self.sessions.drop(session.game_id)
        public = self._public(response)
        public["correct"] = True
        public["user_move"] = move.uci()
        public["user_san"] = user_san
        public["fen_after_user"] = fen_after_user
        public["engine_move"] = engine_move_uci
        public["engine_san"] = engine_san
        public["fen_after_engine"] = fen_after_engine
        return public

    def _engine_play(self, board: chess.Board, variant: str, elo: int) -> chess.Move:
        root_moves = _pawn_legal_moves(board, variant) if variant == "kingless" else None
        return self.engine.choose(board, elo=elo, root_moves=root_moves)

    def _snapshot(self, session: PawnSession, board: chess.Board) -> dict[str, Any]:
        white_material = _material_count(board, chess.WHITE)
        black_material = _material_count(board, chess.BLACK)
        legal_targets = _pawn_legal_targets(board, session.variant)
        game_over, result, reason = _evaluate_endgame(
            board, session.variant, white_material, black_material, legal_targets
        )
        session.game_over = game_over
        session.result = result
        session.result_reason = reason
        return {
            "session": session,
            "board_fen": board.fen(),
            "side_to_move": "white" if board.turn == chess.WHITE else "black",
            "human_color": "white" if session.human_color == chess.WHITE else "black",
            "legal_targets": legal_targets if not game_over else {},
            "white_material": white_material,
            "black_material": black_material,
            "game_over": game_over,
            "result": result,
            "result_reason": reason,
        }

    @staticmethod
    def _public(snapshot: dict[str, Any]) -> dict[str, Any]:
        session: PawnSession = snapshot["session"]
        out = {
            "game_id": session.game_id,
            "variant": session.variant,
            "elo": session.elo,
            "human_color": snapshot["human_color"],
            "side_to_move": snapshot["side_to_move"],
            "board_fen": snapshot["board_fen"],
            "legal_targets": snapshot["legal_targets"],
            "white_material": snapshot["white_material"],
            "black_material": snapshot["black_material"],
            "game_over": snapshot["game_over"],
            "result": snapshot["result"],
            "result_reason": snapshot["result_reason"],
        }
        # Any snapshot-only keys already handled by callers overwriting engine_move/user_move.
        return out


def _king_square(board: chess.Board, color: chess.Color) -> int | None:
    return board.king(color)


def _pawn_legal_moves(board: chess.Board, variant: str) -> list[chess.Move]:
    """All legal moves, optionally excluding king moves for the kingless variant."""
    if variant == "with_kings":
        return list(board.legal_moves)
    king_sq = _king_square(board, board.turn)
    return [move for move in board.legal_moves if move.from_square != king_sq]


def _pawn_legal_targets(board: chess.Board, variant: str) -> dict[str, list[dict[str, str | None]]]:
    result: dict[str, list[dict[str, str | None]]] = {}
    for move in _pawn_legal_moves(board, variant):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        promotion = chess.piece_symbol(move.promotion) if move.promotion else None
        result.setdefault(from_sq, []).append({"to": to_sq, "promotion": promotion})
    return result


def _material_count(board: chess.Board, color: chess.Color) -> int:
    """Non-king material for a side (pawns + any promoted pieces)."""
    total = 0
    for piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        total += len(board.pieces(piece_type, color))
    return total


def _evaluate_endgame(
    board: chess.Board,
    variant: str,
    white_material: int,
    black_material: int,
    legal_targets: dict[str, list[dict[str, str | None]]],
) -> tuple[bool, str | None, str | None]:
    if variant == "kingless":
        if white_material == 0 and black_material == 0:
            return True, "draw", "both sides out of material"
        if white_material == 0:
            return True, "black_wins", "white has no pieces left"
        if black_material == 0:
            return True, "white_wins", "black has no pieces left"
        if not legal_targets:
            loser = "white" if board.turn == chess.WHITE else "black"
            winner = "black_wins" if loser == "white" else "white_wins"
            return True, winner, f"{loser} has no legal pawn moves"
        return False, None, None
    # with_kings variant
    if board.is_checkmate():
        winner = "black_wins" if board.turn == chess.WHITE else "white_wins"
        return True, winner, "checkmate"
    if board.is_stalemate():
        return True, "draw", "stalemate"
    if board.is_insufficient_material():
        return True, "draw", "insufficient material"
    if board.can_claim_fifty_moves() or board.can_claim_threefold_repetition():
        return True, "draw", "fifty-move or threefold rule"
    return False, None, None
