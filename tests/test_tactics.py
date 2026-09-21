from __future__ import annotations

from pathlib import Path

import pytest

from hanging_piece_trainer.app import create_app

SLUG = "tri-band-tactics"
BASE = f"/api/v1/tactics/{SLUG}"


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


HEADERS = {"Origin": "http://localhost"}


def _catalog(app):
    return app.extensions["package_registry"].get(SLUG)


def next_puzzle(client, app):
    """Return a tactics puzzle payload + its expected solution moves."""
    payload = client.get(f"{BASE}/puzzles/next").json
    puzzle = _catalog(app).get(payload["puzzle_id"])
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
        f"{BASE}/moves",
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
        f"{BASE}/moves",
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
        f"{BASE}/moves",
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
            f"{BASE}/moves",
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
    history = client.get(f"{BASE}/attempts").json["attempts"]
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
        f"{BASE}/moves",
        json={"session_id": payload["session_id"], "uci": wrong},
        headers=HEADERS,
    )
    final = _play_full_solution(client, payload["session_id"], solution)
    assert final["completed"] is True
    assert final["point_awarded"] is False


def test_stale_session_returns_404(client) -> None:
    response = client.post(
        f"{BASE}/moves",
        json={"session_id": "not-a-real-session", "uci": "e2e4"},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_tactics_endpoints_reject_cross_origin(client) -> None:
    assert (
        client.post(f"{BASE}/moves", json={}, headers={"Origin": "https://x.com"}).status_code
        == 403
    )


def test_hanging_and_tactics_stats_are_independent(client, app) -> None:
    # A tactics solve should not leak into hanging stats
    payload, solution = next_puzzle(client, app)
    _play_full_solution(client, payload["session_id"], solution)
    hanging_stats = client.get("/api/v1/stats").json
    tactics_stats = client.get(f"{BASE}/stats").json
    assert hanging_stats["attempts"] == 0
    assert tactics_stats["attempts"] == 1


def test_score_for_puzzle_hint_reductions() -> None:
    from hanging_piece_trainer.service import _score_for_puzzle

    # Base cases (unchanged behavior)
    assert _score_for_puzzle(1600, 0) == 16
    assert _score_for_puzzle(1600, 1) == 8
    assert _score_for_puzzle(1600, 2) == 0
    # Theme hints subtract 1 per hint
    assert _score_for_puzzle(1600, 0, hints_used=1) == 15
    assert _score_for_puzzle(1600, 0, hints_used=3) == 13
    # Piece hint subtracts 2
    assert _score_for_puzzle(1600, 0, piece_hint=True) == 14
    # Both hint types stack
    assert _score_for_puzzle(1600, 0, hints_used=2, piece_hint=True) == 12
    # Hints can't push score below 0
    assert _score_for_puzzle(100, 0, hints_used=10) == 0
    # Zero-score puzzle (2+ mistakes) stays at 0
    assert _score_for_puzzle(1600, 2, hints_used=1) == 0


def test_hint_endpoint_reveals_themes_then_piece(client, app) -> None:
    payload, _ = next_puzzle(client, app)
    session_id = payload["session_id"]
    themes = payload["themes"]
    if not themes:
        pytest.skip("puzzle has no themes")
    # First theme hint
    r1 = client.post(
        f"{BASE}/hint",
        json={"session_id": session_id, "type": "theme"},
        headers=HEADERS,
    )
    assert r1.status_code == 200
    assert r1.json["hints_used"] == 1
    assert r1.json["piece_hint"] is False
    assert r1.json["piece_square"] is None
    assert r1.json["themes"] == themes
    # Exhaust all theme hints
    for _ in range(len(themes) - 1):
        client.post(
            f"{BASE}/hint",
            json={"session_id": session_id, "type": "theme"},
            headers=HEADERS,
        )
    # Extra theme call is a no-op (doesn't crash, caps at len(themes))
    r_extra = client.post(
        f"{BASE}/hint",
        json={"session_id": session_id, "type": "theme"},
        headers=HEADERS,
    )
    assert r_extra.json["hints_used"] == len(themes)
    # Piece hint reveals the source square of the first solution move
    r_piece = client.post(
        f"{BASE}/hint",
        json={"session_id": session_id, "type": "piece"},
        headers=HEADERS,
    )
    assert r_piece.status_code == 200
    assert r_piece.json["piece_hint"] is True
    assert r_piece.json["piece_square"]
    catalog_puzzle = _catalog(app).get(payload["puzzle_id"])
    expected_from = catalog_puzzle.solution_moves_uci[0][:2]
    assert r_piece.json["piece_square"] == expected_from


def test_hint_reductions_flow_into_puzzle_points(client, app) -> None:
    payload, solution = next_puzzle(client, app)
    session_id = payload["session_id"]
    themes = payload["themes"] or []
    full_points = payload["batch"]["full_points"]
    # Consume 2 theme hints (or as many as available, up to 2) + piece hint
    theme_calls = min(2, len(themes))
    for _ in range(theme_calls):
        client.post(
            f"{BASE}/hint",
            json={"session_id": session_id, "type": "theme"},
            headers=HEADERS,
        )
    client.post(
        f"{BASE}/hint",
        json={"session_id": session_id, "type": "piece"},
        headers=HEADERS,
    )
    final = _play_full_solution(client, session_id, solution)
    expected_penalty = theme_calls + 2
    assert final["puzzle_points"] == max(0, full_points - expected_penalty)


def test_hint_endpoint_validates_input(client, app) -> None:
    payload, _ = next_puzzle(client, app)
    # Missing type
    r = client.post(
        f"{BASE}/hint",
        json={"session_id": payload["session_id"]},
        headers=HEADERS,
    )
    assert r.status_code == 400
    # Bad type
    r = client.post(
        f"{BASE}/hint",
        json={"session_id": payload["session_id"], "type": "unknown"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    # Missing session_id
    r = client.post(
        f"{BASE}/hint",
        json={"type": "theme"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_mobile_page_renders(client) -> None:
    response = client.get(f"/tactics/{SLUG}/mobile")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="board"' in body
    assert "tactics_mobile.css" in body
    assert "tactics_mobile.js" in body
    # No desktop-view stylesheet on the mobile page.
    assert '"tactics.css"' not in body


def test_desktop_page_redirects_mobile_viewport(client) -> None:
    response = client.get(f"/tactics/{SLUG}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # Mobile detection is loaded as an external same-origin script (kept out
    # of the inline body so it passes the CSP `script-src 'self'` header).
    assert "mobileDetect.js" in body
    # Old mobile subtree no longer served from tactics.html.
    assert 'id="mobile-view"' not in body


def test_mobile_preview_batch_page_renders(client) -> None:
    response = client.get("/tactics/preview/batch/nonexistent/mobile")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-preview-batch="nonexistent"' in body
    assert "tactics_mobile.js" in body


def test_puzzle_public_dict_includes_opening_field(app) -> None:
    catalog = _catalog(app)
    puzzle = catalog.get(catalog._ids[0])
    public = puzzle.public_dict()
    # Field is present (even if None for packages that don't carry openings)
    assert "opening" in public
