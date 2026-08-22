"""Application service for puzzle presentation and authoritative submissions."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import chess

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


class TacticsService:
    """Serves the tactics catalog with Lichess-style solve-mode move validation."""

    def __init__(
        self,
        catalog: PuzzleCatalog,
        repository: ProgressRepository,
        sessions: SolveStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.catalog = catalog
        self.repository = repository
        self.sessions = sessions
        self.now = now

    def next_puzzle(self, previous_id: str | None = None) -> dict[str, Any]:
        puzzle = self.catalog.next(previous_id)
        if not puzzle.solution_moves_uci:
            raise ApplicationError(
                "catalog_error",
                "Puzzle is missing solution moves",
                status=500,
            )
        session_id = self.sessions.create(
            puzzle.puzzle_id, puzzle.presented_fen, list(puzzle.solution_moves_uci)
        )
        public = puzzle.public_dict()
        public["session_id"] = session_id
        public["legal_targets"] = _legal_targets(puzzle.presented_fen)
        public["remaining_plies"] = len(puzzle.solution_moves_uci)
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
        session.submitted_moves.append(uci)
        session.remaining_moves.pop(0)
        board.push(move)
        opponent_uci: str | None = None
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
            board.push(opponent_move)
            session.submitted_moves.append(opponent_uci)
        session.board_fen = board.fen()
        completed = not session.remaining_moves
        response: dict[str, Any] = {
            "correct": True,
            "user_move": uci,
            "opponent_move": opponent_uci,
            "presented_fen": session.board_fen,
            "legal_targets": _legal_targets(session.board_fen) if not completed else {},
            "completed": completed,
            "wrong_moves": session.wrong_moves,
        }
        if completed:
            try:
                puzzle = self.catalog.get(session.puzzle_id)
            except CatalogError as exc:
                raise ApplicationError(
                    "catalog_error", "Puzzle vanished mid-session", status=409
                ) from exc
            point = session.wrong_moves == 0
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
            }
            try:
                self.repository.commit_solve_attempt(attempt)
                statistics = self.repository.solve_stats()
            except RepositoryError as exc:
                raise ApplicationError(
                    "persistence_failure",
                    "Progress could not be saved",
                    status=500,
                    retryable=True,
                ) from exc
            response["point_awarded"] = point
            response["statistics"] = statistics
            response["expected_moves"] = list(puzzle.solution_moves_uci)
            self.sessions.drop(session_id)
        return response


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
