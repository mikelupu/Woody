from __future__ import annotations

from pathlib import Path

import pytest

from hanging_piece_trainer.app import create_app
from hanging_piece_trainer.service import PAWN_ELO_MAX, PAWN_ELO_MIN

HEADERS = {"Origin": "http://localhost"}


def _create_app(tmp_path: Path, *, stockfish_path: str | None = "/opt/homebrew/bin/stockfish"):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "STOCKFISH_PATH": stockfish_path,
        }
    )


@pytest.fixture()
def app(tmp_path: Path):
    return _create_app(tmp_path)


@pytest.fixture()
def client(app):
    return app.test_client()


def _new_kingless(client, *, elo=1500, side="white"):
    return client.post(
        "/api/v1/pawn/new",
        json={"variant": "kingless", "elo": elo, "side": side},
        headers=HEADERS,
    )


def test_engine_unavailable_when_path_missing(tmp_path: Path) -> None:
    app = _create_app(tmp_path, stockfish_path=None)
    client = app.test_client()
    assert client.get("/api/v1/pawn/health").json["state"] == "unavailable"
    response = client.post(
        "/api/v1/pawn/new",
        json={"variant": "kingless", "elo": 1500, "side": "white"},
        headers=HEADERS,
    )
    # No engine needed until human moves (human plays first); black-first would 503.
    # But we ask for side=black to force engine invocation.
    response_black = client.post(
        "/api/v1/pawn/new",
        json={"variant": "kingless", "elo": 1500, "side": "black"},
        headers=HEADERS,
    )
    assert response_black.status_code == 503
    assert response_black.json["error"]["code"] == "engine_unavailable"
    # White-first still needs Stockfish on the next move.
    move_response = client.post(
        "/api/v1/pawn/move",
        json={"game_id": response.json.get("game_id", ""), "uci": "e2e4"},
        headers=HEADERS,
    )
    assert move_response.status_code in (404, 503)  # session absent or engine down


def test_kingless_starting_state_hides_kings(client) -> None:
    payload = _new_kingless(client).json
    assert payload["variant"] == "kingless"
    assert payload["human_color"] == "white"
    assert payload["side_to_move"] == "white"
    assert payload["white_material"] == 8
    assert payload["black_material"] == 8
    # Server has kings in the FEN, but they aren't in legal_targets and no
    # king-square (a1) is offered as a source.
    assert "a1" not in payload["legal_targets"]
    assert "h8" not in payload["legal_targets"]
    # And root_moves-style king moves are filtered from candidate froms.
    for from_sq in payload["legal_targets"]:
        assert from_sq not in {"a1", "h8"}


def test_kingless_rejects_king_moves(client) -> None:
    payload = _new_kingless(client).json
    response = client.post(
        "/api/v1/pawn/move",
        json={"game_id": payload["game_id"], "uci": "a1b1"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json["correct"] is False
    assert response.json["reason"] == "illegal"


def test_kingless_accepts_legal_pawn_move_and_engine_replies(client) -> None:
    payload = _new_kingless(client).json
    response = client.post(
        "/api/v1/pawn/move",
        json={"game_id": payload["game_id"], "uci": "e2e4"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json
    assert body["correct"] is True
    assert body["user_move"] == "e2e4"
    # Stockfish should reply with a pawn move (never a king move).
    assert body["engine_move"] is not None
    engine_from = body["engine_move"][:2]
    assert engine_from != "h8"
    # SAN + intermediate FENs for the moves panel.
    assert body["user_san"] == "e4"
    assert isinstance(body["engine_san"], str) and body["engine_san"]
    assert body["fen_after_user"].startswith("7k/pppppppp"), "fen_after_user should reflect e2-e4"
    assert body["fen_after_engine"] and body["fen_after_engine"] != body["fen_after_user"]


def test_new_game_returns_starting_metadata(client) -> None:
    payload = _new_kingless(client).json
    assert payload["starting_fullmove"] == 1
    assert payload["starting_turn"] == "white"
    assert payload["starting_fen"].startswith("7k/pppppppp/8/8/8/8/PPPPPPPP/K7")


def test_elo_bounds_enforced(client) -> None:
    too_low = client.post(
        "/api/v1/pawn/new",
        json={"variant": "kingless", "elo": PAWN_ELO_MIN - 1, "side": "white"},
        headers=HEADERS,
    )
    assert too_low.status_code == 400
    too_high = client.post(
        "/api/v1/pawn/new",
        json={"variant": "kingless", "elo": PAWN_ELO_MAX + 1, "side": "white"},
        headers=HEADERS,
    )
    assert too_high.status_code == 400


def test_invalid_variant_rejected(client) -> None:
    response = client.post(
        "/api/v1/pawn/new",
        json={"variant": "wild-chess", "elo": 1500, "side": "white"},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_variant"


def test_stale_session_returns_404(client) -> None:
    response = client.post(
        "/api/v1/pawn/move",
        json={"game_id": "no-such-session", "uci": "e2e4"},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_with_kings_starts_with_kings_visible(client) -> None:
    payload = client.post(
        "/api/v1/pawn/new",
        json={"variant": "with_kings", "elo": 1500, "side": "white"},
        headers=HEADERS,
    ).json
    assert payload["variant"] == "with_kings"
    # Kings show up in legal_targets since kings are legal to move
    assert "e1" in payload["legal_targets"]


def test_pawn_endpoints_reject_cross_origin(client) -> None:
    response = client.post(
        "/api/v1/pawn/new",
        json={"variant": "kingless"},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
