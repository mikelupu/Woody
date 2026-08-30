from __future__ import annotations

import json
from pathlib import Path

import pytest

from hanging_piece_trainer.app import create_app
from hanging_piece_trainer.catalog import (
    PackageRegistry,
    PuzzleCatalog,
    checksum,
    curated_packages_dir,
    default_tactics_catalog_path,
)

HEADERS = {"Origin": "http://localhost"}


@pytest.fixture()
def app(tmp_path: Path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "user_packages"),
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


def _write_user_package(user_dir: Path, slug: str, title: str) -> None:
    """Copy the shipped tri-band catalog as a user package under a new slug."""
    data = json.loads(default_tactics_catalog_path().read_text())
    data.pop("catalog_checksum", None)
    data["package"] = {
        "slug": slug,
        "title": title,
        "description": "test copy",
        "kind": "user",
        "created_at": "2026-08-27T00:00:00Z",
        "query": None,
    }
    data["catalog_checksum"] = checksum(data)
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / f"{slug}.json").write_text(json.dumps(data, sort_keys=True, indent=2))


def test_registry_lists_curated_only_by_default(tmp_path: Path) -> None:
    reg = PackageRegistry(curated_packages_dir(), tmp_path / "user")
    slugs = reg.slugs()
    assert "tri-band-tactics" in slugs
    for slug in slugs:
        assert reg.metadata(slug)["kind"] == "curated"


def test_registry_picks_up_user_packages(tmp_path: Path) -> None:
    user_dir = tmp_path / "user"
    _write_user_package(user_dir, "user-a", "User A")
    reg = PackageRegistry(curated_packages_dir(), user_dir)
    assert "user-a" in reg.slugs()
    assert reg.kind("user-a") == "user"
    assert reg.metadata("user-a")["kind"] == "user"


def test_registry_remove_only_user_packages(tmp_path: Path) -> None:
    user_dir = tmp_path / "user"
    _write_user_package(user_dir, "user-b", "User B")
    reg = PackageRegistry(curated_packages_dir(), user_dir)
    reg.remove("user-b")
    assert "user-b" not in reg.slugs()
    from hanging_piece_trainer.catalog import CatalogError

    with pytest.raises(CatalogError):
        reg.remove("tri-band-tactics")


def test_packages_endpoint_lists_curated(client) -> None:
    body = client.get("/api/v1/tactics/packages").json
    slugs = [p["slug"] for p in body["packages"]]
    assert "tri-band-tactics" in slugs
    tri = next(p for p in body["packages"] if p["slug"] == "tri-band-tactics")
    assert tri["kind"] == "curated"
    assert tri["count"] == 100
    assert "progress" in tri
    assert tri["progress"]["batches_per_cycle"] == 20


def test_tactics_redirect_to_packages(client) -> None:
    r = client.get("/tactics", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/tactics/packages")


def test_play_route_bounces_to_picker_for_unknown_slug(client) -> None:
    r = client.get("/tactics/does-not-exist", follow_redirects=False)
    assert r.status_code == 302


def test_api_returns_404_for_unknown_slug(client) -> None:
    r = client.get("/api/v1/tactics/does-not-exist/puzzles/next")
    assert r.status_code == 404


def test_per_package_history_isolated(tmp_path: Path) -> None:
    """Two packages have independent solve_stats + batch history."""
    user_dir = tmp_path / "user"
    _write_user_package(user_dir, "test-copy", "Test Copy")
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(user_dir),
        }
    )
    client = app.test_client()

    reg = app.extensions["package_registry"]
    tri_catalog: PuzzleCatalog = reg.get("tri-band-tactics")
    copy_catalog: PuzzleCatalog = reg.get("test-copy")

    payload = client.get("/api/v1/tactics/tri-band-tactics/puzzles/next").json
    solution = list(tri_catalog.get(payload["puzzle_id"]).solution_moves_uci)
    for uci in solution[::2]:
        client.post(
            "/api/v1/tactics/tri-band-tactics/moves",
            json={"session_id": payload["session_id"], "uci": uci},
            headers=HEADERS,
        )
    tri_stats = client.get("/api/v1/tactics/tri-band-tactics/stats").json
    copy_stats = client.get("/api/v1/tactics/test-copy/stats").json
    assert tri_stats["attempts"] == 1
    assert copy_stats["attempts"] == 0
    # And playing in the second package doesn't leak into the first.
    payload2 = client.get("/api/v1/tactics/test-copy/puzzles/next").json
    solution2 = list(copy_catalog.get(payload2["puzzle_id"]).solution_moves_uci)
    for uci in solution2[::2]:
        client.post(
            "/api/v1/tactics/test-copy/moves",
            json={"session_id": payload2["session_id"], "uci": uci},
            headers=HEADERS,
        )
    tri_stats2 = client.get("/api/v1/tactics/tri-band-tactics/stats").json
    copy_stats2 = client.get("/api/v1/tactics/test-copy/stats").json
    assert tri_stats2["attempts"] == 1  # unchanged
    assert copy_stats2["attempts"] == 1


def test_repository_migrates_legacy_tactics_batches(tmp_path: Path) -> None:
    """Legacy DB with UNIQUE(batch_index, cycle) is rewritten so multiple
    packages can share the same batch/cycle indices without colliding."""
    import sqlite3

    from hanging_piece_trainer.repository import ProgressRepository

    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE schema_meta (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            version INTEGER NOT NULL
        );
        INSERT INTO schema_meta VALUES (1, 1);
        CREATE TABLE attempts (
            attempt_id TEXT PRIMARY KEY, puzzle_id TEXT NOT NULL,
            presented_fen TEXT NOT NULL, scope TEXT NOT NULL,
            effective_colors TEXT NOT NULL, submitted_undefended TEXT NOT NULL,
            submitted_hanging TEXT NOT NULL, expected_undefended TEXT NOT NULL,
            expected_hanging TEXT NOT NULL, feedback TEXT NOT NULL,
            correct INTEGER NOT NULL CHECK (correct IN (0,1)),
            point_awarded INTEGER NOT NULL CHECK (point_awarded IN (0,1)),
            completion_ms INTEGER NOT NULL CHECK (completion_ms >= 0),
            submitted_at TEXT NOT NULL, schema_version INTEGER NOT NULL,
            rules_version TEXT NOT NULL
        );
        CREATE TABLE solve_attempts (
            attempt_id TEXT PRIMARY KEY, puzzle_id TEXT NOT NULL,
            presented_fen TEXT NOT NULL, submitted_moves TEXT NOT NULL,
            expected_moves TEXT NOT NULL,
            wrong_moves INTEGER NOT NULL CHECK (wrong_moves >= 0),
            completed INTEGER NOT NULL CHECK (completed IN (0,1)),
            point_awarded INTEGER NOT NULL CHECK (point_awarded IN (0,1)),
            completion_ms INTEGER NOT NULL CHECK (completion_ms >= 0),
            submitted_at TEXT NOT NULL, schema_version INTEGER NOT NULL,
            rules_version TEXT NOT NULL,
            batch_index INTEGER, cycle INTEGER
        );
        CREATE TABLE tactics_batches (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_index INTEGER NOT NULL, cycle INTEGER NOT NULL,
            completed_at TEXT NOT NULL,
            points_earned INTEGER NOT NULL CHECK (points_earned >= 0),
            points_possible INTEGER NOT NULL CHECK (points_possible >= 0),
            puzzles_solved INTEGER NOT NULL CHECK (puzzles_solved >= 0),
            puzzle_ids TEXT NOT NULL, per_puzzle_points TEXT NOT NULL,
            schema_version INTEGER NOT NULL, rules_version TEXT NOT NULL,
            UNIQUE (batch_index, cycle)
        );
        INSERT INTO tactics_batches (
            batch_index, cycle, completed_at, points_earned,
            points_possible, puzzles_solved, puzzle_ids, per_puzzle_points,
            schema_version, rules_version
        ) VALUES (
            0, 0, '2026-08-27T00:00:00Z', 30, 50, 3,
            '["a","b","c","d","e"]', '[10,10,10,0,0]', 2, '1.0.0'
        );
        """
    )
    conn.commit()
    conn.close()

    repo = ProgressRepository(db_path)
    repo.initialize()

    # Migration preserved the legacy row under the default package.
    assert repo.completed_batches(0) == {0}
    # A second package can now claim the same (batch_index, cycle).
    repo.commit_tactics_batch(
        {
            "batch_index": 0,
            "cycle": 0,
            "completed_at": "2026-08-27T01:00:00Z",
            "points_earned": 20,
            "points_possible": 40,
            "puzzles_solved": 2,
            "puzzle_ids": ["x", "y", "z", "w", "v"],
            "per_puzzle_points": [10, 10, 0, 0, 0],
            "schema_version": 2,
            "rules_version": "1.0.0",
            "package": "other-pkg",
        }
    )
    assert repo.completed_batches(0, package="other-pkg") == {0}
    assert repo.completed_batches(0) == {0}  # tri-band still there
