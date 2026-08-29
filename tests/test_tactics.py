from __future__ import annotations

from pathlib import Path

import pytest

from hanging_piece_trainer.app import create_app


@pytest.fixture()
def app(tmp_path: Path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "progress.sqlite3")})


@pytest.fixture()
def client(app):
    return app.test_client()


HEADERS = {"Origin": "http://localhost"}


def next_puzzle(client, app):
    """Return a tactics puzzle payload + its expected solution moves."""
    payload = client.get("/api/v1/tactics/puzzles/next").json
    catalog = app.extensions["catalog_tactics"]
    puzzle = catalog.get(payload["puzzle_id"])
    return payload, list(puzzle.solution_moves_uci)


def test_next_puzzle_is_playable_and_safe(client, app) -> None:
    payload, solution = next_puzzle(client, app)
    assert payload["session_id"]
    assert payload["remaining_plies"] == len(solution)
    assert payload["legal_targets"]
    assert "answers_by_color" not in payload
    assert "solution_moves_uci" not in payload
    # Metadata for the moves panel.
    assert payload["starting_fullmove"] >= 1
    assert payload["starting_turn"] in ("white", "black")


def test_correct_move_returns_san_and_fen(client, app) -> None:
    payload, solution = next_puzzle(client, app)
    response = client.post(
        "/api/v1/tactics/moves",
        json={"session_id": payload["session_id"], "uci": solution[0]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json
    assert body["correct"] is True
    assert isinstance(body["user_san"], str) and body["user_san"]
    assert body["fen_after_user"], "expected a FEN after the user move"
    if body.get("opponent_move"):
        assert isinstance(body["opponent_san"], str) and body["opponent_san"]
        assert body["fen_after_opponent"], "expected a FEN after the opponent move"


def test_illegal_move_is_rejected_without_advancing(client, app) -> None:
    payload, _ = next_puzzle(client, app)
    response = client.post(
        "/api/v1/tactics/moves",
        json={"session_id": payload["session_id"], "uci": "a1a8"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json
    assert body["correct"] is False
    assert body["reason"] == "illegal"
    assert body["retry"] is True


def test_wrong_but_legal_move_is_rejected_and_counts(client, app) -> None:
    payload, solution = next_puzzle(client, app)
    correct_uci = solution[0]
    wrong_candidates = [
        f"{from_sq}{opt['to']}{opt['promotion'] or ''}"
        for from_sq, options in payload["legal_targets"].items()
        for opt in options
        if f"{from_sq}{opt['to']}{opt['promotion'] or ''}" != correct_uci
    ]
    assert wrong_candidates, "expected at least one legal move that isn't the solution"
    response = client.post(
        "/api/v1/tactics/moves",
        json={"session_id": payload["session_id"], "uci": wrong_candidates[0]},
        headers=HEADERS,
    )
    body = response.json
    assert response.status_code == 200
    assert body["correct"] is False
    assert body["reason"] == "wrong_move"
    assert body["wrong_moves"] == 1


def _play_full_solution(client, session_id: str, solution: list[str]) -> dict:
    """Play the alternating solution (user, opponent, user, ...). Return final response."""
    last = None
    for user_move in solution[::2]:
        response = client.post(
            "/api/v1/tactics/moves",
            json={"session_id": session_id, "uci": user_move},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        last = response.json
        assert last["correct"] is True
        if last["completed"]:
            break
    return last


def test_clean_solve_awards_point_and_persists(client, app) -> None:
    payload, solution = next_puzzle(client, app)
    final = _play_full_solution(client, payload["session_id"], solution)
    assert final["completed"] is True
    assert final["point_awarded"] is True
    assert final["statistics"]["score"] == 1
    assert final["statistics"]["attempts"] == 1
    # History includes the completed attempt
    history = client.get("/api/v1/tactics/attempts").json["attempts"]
    assert history[0]["completed"] is True
    assert history[0]["point_awarded"] is True


def test_solve_with_mistake_completes_without_point(client, app) -> None:
    payload, solution = next_puzzle(client, app)
    correct_uci = solution[0]
    wrong = next(
        f"{from_sq}{opt['to']}{opt['promotion'] or ''}"
        for from_sq, options in payload["legal_targets"].items()
        for opt in options
        if f"{from_sq}{opt['to']}{opt['promotion'] or ''}" != correct_uci
    )
    # One deliberate mistake
    client.post(
        "/api/v1/tactics/moves",
        json={"session_id": payload["session_id"], "uci": wrong},
        headers=HEADERS,
    )
    final = _play_full_solution(client, payload["session_id"], solution)
    assert final["completed"] is True
    assert final["point_awarded"] is False


def test_stale_session_returns_404(client) -> None:
    response = client.post(
        "/api/v1/tactics/moves",
        json={"session_id": "not-a-real-session", "uci": "e2e4"},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_tactics_endpoints_reject_cross_origin(client) -> None:
    assert (
        client.post(
            "/api/v1/tactics/moves", json={}, headers={"Origin": "https://x.com"}
        ).status_code
        == 403
    )


def test_hanging_and_tactics_stats_are_independent(client, app) -> None:
    # A tactics solve should not leak into hanging stats
    payload, solution = next_puzzle(client, app)
    _play_full_solution(client, payload["session_id"], solution)
    hanging_stats = client.get("/api/v1/stats").json
    tactics_stats = client.get("/api/v1/tactics/stats").json
    assert hanging_stats["attempts"] == 0
    assert tactics_stats["attempts"] == 1
