"""Flask application factory and local runtime entrypoint."""

from __future__ import annotations

import hmac
import logging
import os
import shutil
from base64 import b64decode
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for

from .catalog import (
    CatalogError,
    PackageRegistry,
    PuzzleCatalog,
    curated_packages_dir,
    default_catalog_path,
)
from .lichess_index import LichessIndex
from .lichess_themes import CANONICAL_THEMES
from .repository import ProgressRepository, RepositoryError
from .search import ALLOWED_COUNTS, SearchError, query_from_payload, save_search_as_package
from .service import (
    ApplicationError,
    EngineHost,
    PawnGameService,
    PawnSessionStore,
    PresentationStore,
    PreviewBatchStore,
    SolveStore,
    TacticsPreviewService,
    TacticsService,
    TrainingService,
)

DEFAULT_TACTICS_SLUG = "tri-band-tactics"


def _data_root() -> Path:
    """Runtime-writable data root (git-ignored; volume-mounted on Railway)."""
    return Path(os.environ.get("HPT_DATA_DIR", Path.cwd() / "data")).resolve()


def _user_packages_dir(app: Flask) -> Path:
    """Runtime-writable directory for user-created tactics packages."""
    override = app.config.get("USER_PACKAGES_DIR")
    if override:
        return Path(override)
    return _data_root() / "packages"


def _lichess_source_path(app: Flask) -> Path:
    override = app.config.get("LICHESS_SOURCE_PATH")
    if override:
        return Path(override)
    return _data_root() / "source" / "lichess_db_puzzle.csv.zst"


def _lichess_index_path(app: Flask) -> Path:
    override = app.config.get("LICHESS_INDEX_PATH")
    if override:
        return Path(override)
    return _data_root() / "lichess_index.sqlite3"


def create_app(config: dict[str, Any] | None = None) -> Flask:
    instance_path = Path(os.environ.get("HPT_INSTANCE_PATH", Path.cwd() / "instance")).resolve()
    app = Flask(__name__, instance_relative_config=True, instance_path=str(instance_path))
    app.config.from_mapping(
        CATALOG_PATH=str(default_catalog_path()),
        CURATED_PACKAGES_DIR=str(curated_packages_dir()),
        USER_PACKAGES_DIR=None,
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

    packages_error: str | None = None
    package_registry: PackageRegistry | None = None
    try:
        package_registry = PackageRegistry(
            Path(app.config["CURATED_PACKAGES_DIR"]),
            _user_packages_dir(app),
        )
    except OSError as exc:
        packages_error = str(exc)
        app.logger.error("Package registry initialisation failed: %s", exc)

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

    engine_host = EngineHost(app.config.get("STOCKFISH_PATH"))
    pawn_service = PawnGameService(
        engine_host, PawnSessionStore(ttl_seconds=app.config["PRESENTATION_TTL_SECONDS"])
    )

    lichess_index = LichessIndex(
        _lichess_index_path(app),
        source_path=_lichess_source_path(app),
    )
    preview_service = TacticsPreviewService(
        SolveStore(ttl_seconds=app.config["PRESENTATION_TTL_SECONDS"])
    )
    preview_batch_store = PreviewBatchStore(ttl_seconds=app.config["PRESENTATION_TTL_SECONDS"])

    tactics_services: dict[str, TacticsService] = {}

    def require_tactics(slug: str) -> TacticsService:
        if database_error is not None or package_registry is None:
            raise ApplicationError(
                "not_ready",
                "Tactics mode is unavailable; check the local health endpoint",
                status=503,
            )
        try:
            package_catalog = package_registry.get(slug)
        except CatalogError as exc:
            raise ApplicationError(
                "unknown_package", f"No tactics package named {slug!r}", status=404
            ) from exc
        service = tactics_services.get(slug)
        if service is None:
            service = TacticsService(
                package_catalog,
                repository,
                SolveStore(ttl_seconds=app.config["PRESENTATION_TTL_SECONDS"]),
                package=slug,
            )
            tactics_services[slug] = service
        return service

    app.extensions["catalog"] = catalog
    app.extensions["repository"] = repository
    app.extensions["training_service"] = training_service
    app.extensions["engine"] = engine_host
    app.extensions["pawn_service"] = pawn_service
    app.extensions["package_registry"] = package_registry
    app.extensions["tactics_services"] = tactics_services
    app.extensions["lichess_index"] = lichess_index
    app.extensions["preview_service"] = preview_service
    app.extensions["preview_batch_store"] = preview_batch_store

    def require_training() -> TrainingService:
        current = app.extensions["training_service"]
        if current is None:
            raise ApplicationError(
                "not_ready",
                "Training is unavailable; check the local health endpoint",
                status=503,
            )
        return current

    basic_user = os.environ.get("HPT_BASIC_USER")
    basic_pass = os.environ.get("HPT_BASIC_PASS")

    @app.before_request
    def basic_auth_gate():
        if not basic_user or not basic_pass:
            return None  # Auth disabled (local dev)
        # Health endpoint is publicly reachable so hosting platforms can probe it.
        if request.path == "/api/v1/health":
            return None
        header = request.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = b64decode(header[6:], validate=True).decode("utf-8")
                submitted_user, _, submitted_pass = decoded.partition(":")
            except (ValueError, UnicodeDecodeError):
                submitted_user = submitted_pass = ""
            if hmac.compare_digest(submitted_user, basic_user) and hmac.compare_digest(
                submitted_pass, basic_pass
            ):
                return None
        return Response(
            "Authentication required",
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Hanging Piece Trainer"'},
        )

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

    @app.get("/favicon.ico")
    def favicon_ico():
        # Root-relative favicon fallback for browsers that always request
        # /favicon.ico regardless of the <link rel="icon"> tags in the page.
        return app.send_static_file("favicon-32.png")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/minigame")
    def minigame():
        return render_template("minigame.html")

    @app.get("/tactics")
    def tactics_page():
        return redirect(url_for("tactics_packages_page"))

    @app.get("/tactics/packages")
    def tactics_packages_page():
        return render_template("packages.html")

    @app.get("/tactics/packages/new")
    def tactics_packages_new_page():
        return render_template("search_builder.html")

    @app.get("/tactics/preview/batch/<batch_id>")
    def tactics_preview_batch_page(batch_id: str):
        return render_template(
            "tactics.html",
            slug="__preview__",
            preview_batch=batch_id,
        )

    @app.get("/tactics/<slug>")
    def tactics_play_page(slug: str):
        if slug == "preview":
            return redirect(url_for("tactics_packages_page"))
        if package_registry is None or slug not in package_registry.slugs():
            return redirect(url_for("tactics_packages_page"))
        return render_template("tactics.html", slug=slug)

    @app.get("/tactics/<slug>/stats")
    def tactics_stats_page(slug: str):
        if package_registry is None or slug not in package_registry.slugs():
            return redirect(url_for("tactics_packages_page"))
        return render_template("tactics_stats.html", slug=slug)

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

    @app.get("/api/v1/tactics/packages")
    def tactics_packages_list():
        if package_registry is None:
            raise ApplicationError("not_ready", "Tactics packages are unavailable", status=503)
        rows: list[dict[str, Any]] = []
        for slug in package_registry.slugs():
            meta = dict(package_registry.metadata(slug))
            try:
                service = require_tactics(slug)
                cycle = repository.current_cycle(service.batches_per_cycle, package=slug)
                done_in_cycle = len(repository.completed_batches(cycle, package=slug))
                stats = repository.tactics_batch_stats(package=slug)
            except (ApplicationError, RepositoryError):
                cycle = 0
                done_in_cycle = 0
                stats = {"batches": 0, "total_earned": 0, "total_possible": 0}
            meta["progress"] = {
                "cycle": cycle,
                "batches_completed_in_cycle": done_in_cycle,
                "batches_per_cycle": service.batches_per_cycle
                if slug in tactics_services
                else max(1, meta["count"] // 5),
                "batches_completed_total": stats.get("batches", 0),
                "points_earned": stats.get("total_earned", 0),
                "points_possible": stats.get("total_possible", 0),
            }
            rows.append(meta)
        return jsonify({"packages": rows})

    @app.get("/api/v1/tactics/<slug>/puzzles/next")
    def next_tactic(slug: str):
        previous_id = request.args.get("previous_id")
        return jsonify(require_tactics(slug).next_puzzle(previous_id))

    @app.post("/api/v1/tactics/<slug>/moves")
    def submit_tactic_move(slug: str):
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(require_tactics(slug).submit_move(payload))

    @app.post("/api/v1/tactics/<slug>/reveal")
    def submit_tactic_reveal(slug: str):
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(require_tactics(slug).reveal(payload))

    @app.get("/api/v1/tactics/<slug>/stats")
    def tactic_stats(slug: str):
        require_tactics(slug)
        return jsonify(repository.solve_stats(package=slug))

    @app.get("/api/v1/tactics/<slug>/batches")
    def tactic_batches(slug: str):
        require_tactics(slug)
        try:
            limit = int(request.args.get("limit", "100"))
            offset = int(request.args.get("offset", "0"))
        except ValueError as exc:
            raise ApplicationError(
                "invalid_pagination", "Pagination values must be integers"
            ) from exc
        return jsonify(
            {
                "batches": repository.tactics_batch_history(
                    limit=limit, offset=offset, package=slug
                ),
                "statistics": repository.tactics_batch_stats(package=slug),
                "limit": limit,
                "offset": offset,
            }
        )

    @app.get("/api/v1/tactics/index/status")
    def tactics_index_status():
        return jsonify(lichess_index.status())

    @app.post("/api/v1/tactics/index/build")
    def tactics_index_build():
        _require_same_origin_json()
        if not lichess_index.source_available():
            raise ApplicationError(
                "source_missing",
                "Lichess source dump not found at "
                f"{lichess_index.source_path}. Upload the dump and retry.",
                status=409,
            )
        started = lichess_index.build_async()
        if not started:
            raise ApplicationError("already_running", "Index build already in progress", status=409)
        return jsonify(lichess_index.status()), 202

    @app.get("/api/v1/tactics/search/themes")
    def tactics_search_themes():
        return jsonify({"themes": list(CANONICAL_THEMES)})

    @app.get("/api/v1/tactics/search/opening-tags")
    def tactics_search_opening_tags():
        if lichess_index.status()["state"] != "ready":
            raise ApplicationError(
                "index_not_ready",
                "Search index has not been built yet",
                status=409,
            )
        return jsonify({"opening_tags": lichess_index.opening_tags()})

    @app.post("/api/v1/tactics/preview/start")
    def tactics_preview_start():
        _require_same_origin_json()
        if lichess_index.status()["state"] != "ready":
            raise ApplicationError(
                "index_not_ready",
                "Search index has not been built yet",
                status=409,
            )
        payload = request.get_json(silent=True) or {}
        puzzle_id = str(payload.get("puzzle_id") or "").strip()
        if not puzzle_id:
            raise ApplicationError("invalid_request", "puzzle_id is required")
        with lichess_index._connect() as connection:
            row = connection.execute(
                "SELECT id, fen, moves, rating, themes, game_url FROM puzzles WHERE id = ?",
                (puzzle_id,),
            ).fetchone()
        if row is None:
            raise ApplicationError(
                "unknown_puzzle", f"no puzzle {puzzle_id!r} in the local index", status=404
            )
        puzzle_row = {
            "id": row["id"],
            "fen": row["fen"],
            "moves": row["moves"],
            "rating": row["rating"],
            "themes": row["themes"].split() if row["themes"] else [],
            "game_url": row["game_url"],
        }
        return jsonify(preview_service.start(puzzle_row))

    @app.post("/api/v1/tactics/preview/moves")
    def tactics_preview_move():
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(preview_service.submit_move(payload))

    @app.post("/api/v1/tactics/preview/reveal")
    def tactics_preview_reveal():
        _require_same_origin_json()
        payload = request.get_json(silent=True)
        if payload is None:
            raise ApplicationError("invalid_json", "A JSON request body is required")
        return jsonify(preview_service.reveal(payload))

    @app.post("/api/v1/tactics/preview/batch")
    def tactics_preview_batch_create():
        _require_same_origin_json()
        if lichess_index.status()["state"] != "ready":
            raise ApplicationError(
                "index_not_ready",
                "Search index has not been built yet",
                status=409,
            )
        payload = request.get_json(silent=True) or {}
        try:
            query = query_from_payload(payload)
        except SearchError as exc:
            raise ApplicationError(exc.code, str(exc)) from exc
        ranked = lichess_index.matching_ids_ranked(query, limit=10)
        if not ranked:
            raise ApplicationError("no_matches", "No puzzles matched this query", status=409)
        rows = [
            {
                "id": row["id"],
                "fen": row["fen"],
                "moves": row["moves"],
                "rating": row["rating"],
                "themes": row["themes"].split() if row.get("themes") else [],
                "game_url": row.get("game_url"),
            }
            for row in ranked
        ]
        batch_id = preview_batch_store.create(rows)
        return jsonify(
            {
                "batch_id": batch_id,
                "puzzle_ids": [row["id"] for row in rows],
                "count": len(rows),
            }
        )

    @app.get("/api/v1/tactics/preview/batch/<batch_id>")
    def tactics_preview_batch_get(batch_id: str):
        rows = preview_batch_store.resolve(batch_id)
        return jsonify(
            {
                "batch_id": batch_id,
                "puzzle_ids": [row["id"] for row in rows],
                "count": len(rows),
            }
        )

    @app.post("/api/v1/tactics/preview/batch/<batch_id>/start")
    def tactics_preview_batch_start(batch_id: str):
        _require_same_origin_json()
        rows = preview_batch_store.resolve(batch_id)
        payload = request.get_json(silent=True) or {}
        index = payload.get("index", 0)
        try:
            index = int(index)
        except (TypeError, ValueError) as exc:
            raise ApplicationError("invalid_request", "index must be an integer") from exc
        if not 0 <= index < len(rows):
            raise ApplicationError(
                "index_out_of_range", f"index {index} outside 0..{len(rows) - 1}", status=400
            )
        response = preview_service.start(rows[index])
        response["batch_index"] = index
        response["batch_total"] = len(rows)
        return jsonify(response)

    @app.post("/api/v1/tactics/search/preview")
    def tactics_search_preview():
        _require_same_origin_json()
        if lichess_index.status()["state"] != "ready":
            raise ApplicationError(
                "index_not_ready",
                "Search index has not been built yet",
                status=409,
            )
        payload = request.get_json(silent=True) or {}
        try:
            query = query_from_payload(payload)
        except SearchError as exc:
            raise ApplicationError(exc.code, str(exc)) from exc
        preview = lichess_index.preview(query)
        return jsonify(
            {
                "count": preview.count,
                "sample": preview.sample,
                "rating_histogram": preview.rating_histogram,
                "allowed_counts": list(ALLOWED_COUNTS),
            }
        )

    @app.post("/api/v1/tactics/packages")
    def tactics_packages_create():
        _require_same_origin_json()
        if package_registry is None:
            raise ApplicationError("not_ready", "Package registry unavailable", status=503)
        if lichess_index.status()["state"] != "ready":
            raise ApplicationError(
                "index_not_ready",
                "Search index has not been built yet",
                status=409,
            )
        payload = request.get_json(silent=True) or {}
        pkg_meta = payload.get("package") or {}
        query_payload = payload.get("query") or {}
        slug = str(pkg_meta.get("slug", "")).strip()
        title = str(pkg_meta.get("title") or slug).strip()
        description = str(pkg_meta.get("description") or "").strip()
        try:
            query = query_from_payload(query_payload)
        except SearchError as exc:
            raise ApplicationError(exc.code, str(exc), status=400) from exc
        try:
            path, catalog_obj = save_search_as_package(
                lichess_index,
                query=query,
                slug=slug,
                title=title or slug,
                description=description,
                existing_slugs=set(package_registry.slugs()),
                output_dir=_user_packages_dir(app),
            )
        except SearchError as exc:
            status = 409 if exc.code == "slug_in_use" else 400
            raise ApplicationError(exc.code, str(exc), status=status) from exc
        package_registry.register_user_package(catalog_obj, path)
        # Drop any stale cached service under this slug so it uses the new catalog.
        tactics_services.pop(slug, None)
        return (
            jsonify(
                {
                    "slug": catalog_obj.slug,
                    "count": catalog_obj.target_count,
                    "path": str(path),
                    "package": catalog_obj.package,
                }
            ),
            201,
        )

    @app.delete("/api/v1/tactics/packages/<slug>")
    def tactics_packages_delete(slug: str):
        _require_same_origin_json_delete()
        if package_registry is None:
            raise ApplicationError("not_ready", "Package registry unavailable", status=503)
        try:
            if package_registry.kind(slug) != "user":
                raise ApplicationError(
                    "forbidden",
                    "Only user-built packages can be deleted",
                    status=403,
                )
            package_registry.remove(slug)
        except CatalogError as exc:
            raise ApplicationError("unknown_package", str(exc), status=404) from exc
        tactics_services.pop(slug, None)
        return jsonify({"slug": slug, "deleted": True})

    @app.get("/api/v1/tactics/<slug>/attempts")
    def tactic_attempts(slug: str):
        require_tactics(slug)
        try:
            limit = int(request.args.get("limit", "100"))
            offset = int(request.args.get("offset", "0"))
        except ValueError as exc:
            raise ApplicationError(
                "invalid_pagination", "Pagination values must be integers"
            ) from exc
        rows = repository.solve_history(limit=limit, offset=offset, package=slug)
        return jsonify({"attempts": rows, "limit": limit, "offset": offset})

    @app.get("/api/v1/health")
    def health():
        hanging_ready = training_service is not None
        tactics_ready = package_registry is not None and bool(package_registry.slugs())
        overall_ready = hanging_ready or tactics_ready
        return (
            jsonify(
                {
                    "status": "ready" if overall_ready else "unavailable",
                    "catalog": "ready" if catalog is not None else catalog_error,
                    "packages": ("ready" if package_registry is not None else packages_error),
                    "database": "ready" if database_error is None else database_error,
                    "engine": engine_host.status(),
                }
            ),
            200 if overall_ready else 503,
        )

    def _require_same_origin_json() -> None:
        if not request.is_json:
            raise ApplicationError("json_required", "Mutation requests must use JSON", status=415)
        _require_same_origin()

    def _require_same_origin_json_delete() -> None:
        # DELETE without a body is fine; still require same-origin.
        _require_same_origin()

    def _require_same_origin() -> None:
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
