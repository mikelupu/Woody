from __future__ import annotations

from pathlib import Path

import pytest

from hanging_piece_trainer.app import create_app
from hanging_piece_trainer.domain import Scope


@pytest.fixture()
def app(tmp_path: Path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "progress.sqlite3")})


@pytest.fixture()
def client(app):
    return app.test_client()


def test_shell_health_and_security_headers(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hanging Piece Trainer" in response.data
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert client.get("/api/v1/health").json["status"] == "ready"


def test_public_puzzle_is_answer_free(client) -> None:
    response = client.get("/api/v1/puzzles/next")
    assert response.status_code == 200
    assert "answers_by_color" not in response.json
    assert "presentation_id" in response.json


def test_submission_requires_json_and_same_origin(client) -> None:
    assert client.post("/api/v1/attempts", data="x").status_code == 415
    assert client.post("/api/v1/attempts", json={}).status_code == 403
    response = client.post(
        "/api/v1/attempts", json={}, headers={"Origin": "https://attacker.example"}
    )
    assert response.status_code == 403


def test_exact_submission_commits_and_replays(client, app) -> None:
    public = client.get("/api/v1/puzzles/next").json
    catalog = app.extensions["catalog"]
    expected = catalog.expected(public["puzzle_id"], Scope.SIDE_TO_MOVE)
    payload = {
        "attempt_id": "attempt-exact-1",
        "presentation_id": public["presentation_id"],
        "scope": "side_to_move",
        "hanging": sorted(expected.hanging),
        "completion_ms": 1250,
    }
    headers = {"Origin": "http://localhost"}
    response = client.post("/api/v1/attempts", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json["point_awarded"] is True
    assert "undefended" not in response.json["expected"]
    assert set(response.json["feedback"]) == {"hanging"}
    assert response.json["statistics"]["score"] == 1
    replay = client.post("/api/v1/attempts", json=payload, headers=headers)
    assert replay.json["replayed"] is True
    assert replay.json["statistics"]["attempts"] == 1
    assert client.get("/api/v1/attempts").json["attempts"][0]["attempt_id"] == "attempt-exact-1"


def test_committed_attempt_replays_after_application_restart(tmp_path: Path) -> None:
    database = tmp_path / "progress.sqlite3"
    first_app = create_app({"TESTING": True, "DATABASE": str(database)})
    first_client = first_app.test_client()
    public = first_client.get("/api/v1/puzzles/next").json
    expected = first_app.extensions["catalog"].expected(public["puzzle_id"], Scope.SIDE_TO_MOVE)
    payload = {
        "attempt_id": "restart-replay-1",
        "presentation_id": public["presentation_id"],
        "scope": "side_to_move",
        "hanging": sorted(expected.hanging),
        "completion_ms": 50,
    }
    headers = {"Origin": "http://localhost"}
    assert first_client.post("/api/v1/attempts", json=payload, headers=headers).status_code == 200
    restarted = create_app({"TESTING": True, "DATABASE": str(database)}).test_client()
    payload["presentation_id"] = "expired-after-restart"
    replay = restarted.post("/api/v1/attempts", json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json["replayed"] is True


def test_invalid_submission_does_not_commit(client) -> None:
    public = client.get("/api/v1/puzzles/next").json
    payload = {
        "attempt_id": "attempt-invalid-1",
        "presentation_id": public["presentation_id"],
        "scope": "side_to_move",
        "hanging": ["z9"],
        "completion_ms": 1,
    }
    response = client.post("/api/v1/attempts", json=payload, headers={"Origin": "http://localhost"})
    assert response.status_code == 400
    assert client.get("/api/v1/stats").json["attempts"] == 0


def test_unknown_presentation_and_pagination_errors(client) -> None:
    payload = {
        "attempt_id": "attempt-stale-1",
        "presentation_id": "missing",
        "scope": "both",
        "hanging": [],
        "completion_ms": 0,
    }
    response = client.post("/api/v1/attempts", json=payload, headers={"Origin": "http://localhost"})
    assert response.status_code == 404
    assert client.get("/api/v1/attempts?limit=bad").status_code == 400


def test_missing_hanging_catalog_reports_unavailable(tmp_path: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "CATALOG_PATH": str(tmp_path / "missing.json"),
            "CURATED_PACKAGES_DIR": str(tmp_path / "no-packages"),
            "USER_PACKAGES_DIR": str(tmp_path / "user_packages"),
        }
    )
    client = app.test_client()
    # No hanging catalog and no packages → health is 503.
    assert client.get("/api/v1/health").status_code == 503
    assert client.get("/api/v1/puzzles/next").status_code == 503
    # Unknown tactics package returns 404 (not 503) — the registry is up but empty.
    assert client.get("/api/v1/tactics/nope/puzzles/next").status_code == 404


def test_hanging_endpoints_still_work_when_no_tactics_packages(tmp_path: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "CURATED_PACKAGES_DIR": str(tmp_path / "no-packages"),
            "USER_PACKAGES_DIR": str(tmp_path / "user_packages"),
        }
    )
    client = app.test_client()
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json["catalog"] == "ready"
    assert client.get("/api/v1/puzzles/next").status_code == 200
    # Tactics packages list is empty; individual slug lookups 404.
    assert client.get("/api/v1/tactics/packages").json["packages"] == []
    assert client.get("/api/v1/tactics/nope/puzzles/next").status_code == 404


def test_not_found_is_stable_json(client) -> None:
    response = client.get("/missing")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "not_found"


def test_basic_auth_gate_when_env_vars_set(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HPT_BASIC_USER", "captain")
    monkeypatch.setenv("HPT_BASIC_PASS", "s3cret")
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "progress.sqlite3")})
    client = app.test_client()
    # No credentials -> 401 + WWW-Authenticate
    unauthorized = client.get("/")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["WWW-Authenticate"].startswith("Basic ")
    # Wrong credentials -> 401
    from base64 import b64encode

    bad = b64encode(b"captain:wrong").decode()
    assert client.get("/", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    # Right credentials -> 200
    good = b64encode(b"captain:s3cret").decode()
    assert client.get("/", headers={"Authorization": f"Basic {good}"}).status_code == 200
    # Health endpoint stays public for platform probes.
    assert client.get("/api/v1/health").status_code in (200, 503)
