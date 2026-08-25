"""Flask application factory and local runtime entrypoint."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request

from .catalog import (
    CatalogError,
    PuzzleCatalog,
    default_catalog_path,
    default_tactics_catalog_path,
)
from .repository import ProgressRepository, RepositoryError
from .service import (
    ApplicationError,
    EngineHost,
    PawnGameService,
    PawnSessionStore,
    PresentationStore,
    SolveStore,
    TacticsService,
    TrainingService,
)


def create_app(config: dict[str, Any] | None = None) -> Flask:
    instance_path = Path(os.environ.get("HPT_INSTANCE_PATH", Path.cwd() / "instance")).resolve()
    app = Flask(__name__, instance_relative_config=True, instance_path=str(instance_path))
    app.config.from_mapping(
        CATALOG_PATH=str(default_catalog_path()),
        CATALOG_TACTICS_PATH=os.environ.get(
            "HPT_TACTICS_CATALOG_PATH", str(default_tactics_catalog_path())
        ),
        STOCKFISH_PATH=_resolve_stockfish_path(),
        DATABASE=str(Path(app.instance_path) / "progress.sqlite3"),
        PRESENTATION_TTL_SECONDS=7200,
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    catalog_error: str | None = None
    try:
        catalog = PuzzleCatalog.load(Path(app.config["CATALOG_PATH"]))
    except CatalogError as exc:
        catalog = None
        catalog_error = str(exc)
        app.logger.error("Catalog validation failed: %s", exc)

    catalog_tactics_error: str | None = None
    try:
        catalog_tactics = PuzzleCatalog.load(Path(app.config["CATALOG_TACTICS_PATH"]))
    except CatalogError as exc:
        catalog_tactics = None
        catalog_tactics_error = str(exc)
        app.logger.error("Tactics catalog validation failed: %s", exc)

    repository = ProgressRepository(Path(app.config["DATABASE"]))
    database_error: str | None = None
    try:
        repository.initialize()
    except RepositoryError as exc:
        database_error = str(exc)
        app.logger.error("Progress initialization failed: %s", exc)

    training_service = (
        TrainingService(
            catalog,
            repository,
            PresentationStore(ttl_seconds=app.config["PRESENTATION_TTL_SECONDS"]),
        )
        if catalog is not None and database_error is None
        else None
    )
    tactics_service = (
        TacticsService(
            catalog_tactics,
            repository,
            SolveStore(ttl_seconds=app.config["PRESENTATION_TTL_SECONDS"]),
        )
        if catalog_tactics is not None and database_error is None
        else None
    )

    engine_host = EngineHost(app.config.get("STOCKFISH_PATH"))
    pawn_service = PawnGameService(
        engine_host, PawnSessionStore(ttl_seconds=app.config["PRESENTATION_TTL_SECONDS"])
    )

    app.extensions["catalog"] = catalog
    app.extensions["catalog_tactics"] = catalog_tactics
    app.extensions["repository"] = repository
    app.extensions["training_service"] = training_service
    app.extensions["tactics_service"] = tactics_service
    app.extensions["engine"] = engine_host
    app.extensions["pawn_service"] = pawn_service

    def require_training() -> TrainingService:
        current = app.extensions["training_service"]
        if current is None:
            raise ApplicationError(
                "not_ready",
                "Training is unavailable; check the local health endpoint",
                status=503,
            )
        return current

    def require_tactics() -> TacticsService:
        current = app.extensions["tactics_service"]
        if current is None:
            raise ApplicationError(
                "not_ready",
                "Tactics mode is unavailable; check the local health endpoint",
                status=503,
            )
        return current

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ApplicationError)
    def application_error(error: ApplicationError):
        return (
            jsonify(
                {
                    "error": {
                        "code": error.code,
                        "message": str(error),
                        "retryable": error.retryable,
                    }
                }
            ),
            error.status,
        )

    @app.errorhandler(RepositoryError)
    def repository_error(_error: RepositoryError):
        return (
            jsonify(
                {
                    "error": {
                        "code": "progress_unavailable",
                        "message": "Progress is temporarily unavailable",
                        "retryable": True,
                    }
                }
            ),
            500,
        )

    @app.errorhandler(404)
    def not_found(_error):
        payload = {"error": {"code": "not_found", "message": "Not found", "retryable": False}}
        return jsonify(payload), 404

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/minigame")
    def minigame():
        return render_template("minigame.html")

    @app.get("/tactics")
    def tactics_page():
        return render_template("tactics.html")

    @app.get("/tactics/stats")
    def tactics_stats_page():
        return render_template("tactics_stats.html")

    @app.get("/pawn-war")
    def pawn_page():
        return render_template("pawn.html")

    @app.get("/api/v1/puzzles/next")
    def next_puzzle():
        previous_id = request.args.get("previous_id")
        return jsonify(require_training().next_puzzle(previous_id))

    @app.post("/api/v1/attempts")
    def submit_attempt():
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(require_training().submit(payload))

    @app.get("/api/v1/stats")
    def stats():
        require_training()
        return jsonify(repository.stats())

    @app.get("/api/v1/attempts")
    def attempts():
        require_training()
        try:
            limit = int(request.args.get("limit", "100"))
            offset = int(request.args.get("offset", "0"))
        except ValueError as exc:
            raise ApplicationError(
                "invalid_pagination", "Pagination values must be integers"
            ) from exc
        rows = repository.history(limit=limit, offset=offset)
        return jsonify({"attempts": rows, "limit": limit, "offset": offset})

    @app.post("/api/v1/pawn/new")
    def pawn_new():
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(pawn_service.new_game(payload))

    @app.post("/api/v1/pawn/move")
    def pawn_move():
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(pawn_service.submit_move(payload))

    @app.get("/api/v1/pawn/health")
    def pawn_health():
        return jsonify(engine_host.status())

    @app.get("/api/v1/tactics/puzzles/next")
    def next_tactic():
        previous_id = request.args.get("previous_id")
        return jsonify(require_tactics().next_puzzle(previous_id))

    @app.post("/api/v1/tactics/moves")
    def submit_tactic_move():
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(require_tactics().submit_move(payload))

    @app.post("/api/v1/tactics/reveal")
    def submit_tactic_reveal():
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(require_tactics().reveal(payload))

    @app.get("/api/v1/tactics/stats")
    def tactic_stats():
        require_tactics()
        return jsonify(repository.solve_stats())

    @app.get("/api/v1/tactics/batches")
    def tactic_batches():
        require_tactics()
        try:
            limit = int(request.args.get("limit", "100"))
            offset = int(request.args.get("offset", "0"))
        except ValueError as exc:
            raise ApplicationError(
                "invalid_pagination", "Pagination values must be integers"
            ) from exc
        return jsonify(
            {
                "batches": repository.tactics_batch_history(limit=limit, offset=offset),
                "statistics": repository.tactics_batch_stats(),
                "limit": limit,
                "offset": offset,
            }
        )

    @app.get("/api/v1/tactics/attempts")
    def tactic_attempts():
        require_tactics()
        try:
            limit = int(request.args.get("limit", "100"))
            offset = int(request.args.get("offset", "0"))
        except ValueError as exc:
            raise ApplicationError(
                "invalid_pagination", "Pagination values must be integers"
            ) from exc
        rows = repository.solve_history(limit=limit, offset=offset)
        return jsonify({"attempts": rows, "limit": limit, "offset": offset})

    @app.get("/api/v1/health")
    def health():
        hanging_ready = training_service is not None
        tactics_ready = tactics_service is not None
        overall_ready = hanging_ready or tactics_ready
        return (
            jsonify(
                {
                    "status": "ready" if overall_ready else "unavailable",
                    "catalog": "ready" if catalog is not None else catalog_error,
                    "catalog_tactics": (
                        "ready" if catalog_tactics is not None else catalog_tactics_error
                    ),
                    "database": "ready" if database_error is None else database_error,
                    "engine": engine_host.status(),
                }
            ),
            200 if overall_ready else 503,
        )

    def _require_same_origin_json() -> None:
        if not request.is_json:
            raise ApplicationError("json_required", "Mutation requests must use JSON", status=415)
        origin = request.headers.get("Origin")
        if not origin:
            raise ApplicationError(
                "origin_required", "Mutation request origin is required", status=403
            )
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != request.host:
            raise ApplicationError("origin_rejected", "Cross-origin mutation rejected", status=403)

    return app


def _resolve_stockfish_path() -> str | None:
    override = os.environ.get("HPT_STOCKFISH_PATH")
    if override and Path(override).exists():
        return override
    discovered = shutil.which("stockfish")
    return discovered


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
