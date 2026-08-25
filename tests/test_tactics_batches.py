from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from hanging_piece_trainer.app import create_app
from hanging_piece_trainer.catalog import PuzzleCatalog, default_tactics_catalog_path
from hanging_piece_trainer.service import (
    TACTICS_BATCH_SIZE,
    _score_for_puzzle,
    compute_batches,
)

HEADERS = {"Origin": "http://localhost"}


@pytest.fixture(scope="module")
def catalog() -> PuzzleCatalog:
    return PuzzleCatalog.load(default_tactics_catalog_path())


@pytest.fixture()
def app(tmp_path: Path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "progress.sqlite3")})


@pytest.fixture()
def client(app):
    return app.test_client()


def test_compute_batches_covers_catalog_once(catalog: PuzzleCatalog) -> None:
    batches = compute_batches(catalog)
    assert len(batches) == len(catalog._ids) // TACTICS_BATCH_SIZE
    seen: set[str] = set()
    for batch in batches:
        assert len(batch.puzzle_ids) == TACTICS_BATCH_SIZE
        for pid in batch.puzzle_ids:
            assert pid not in seen
            seen.add(pid)
    assert seen == set(catalog._ids)


def test_compute_batches_is_balanced(catalog: PuzzleCatalog) -> None:
    batches = compute_batches(catalog)
    totals = [b.total_rating for b in batches]
    # Stddev of batch ratings should be small — LPT is near-optimal.
    assert statistics.pstdev(totals) < 200


def test_score_helper_matches_specification() -> None:
    # Full points at 0 wrong moves
    assert _score_for_puzzle(400, 0) == 4
    assert _score_for_puzzle(1000, 0) == 10
    assert _score_for_puzzle(1800, 0) == 18
    # Half points on 1 mistake
    assert _score_for_puzzle(400, 1) == 2
    assert _score_for_puzzle(1000, 1) == 5
    # Zero for 2+ mistakes
    assert _score_for_puzzle(1000, 2) == 0
    assert _score_for_puzzle(2500, 5) == 0


def _solve_puzzle(client, app, *, mistakes: int) -> dict:
    """Play the current tactics puzzle, optionally inserting `mistakes` wrong moves."""
    payload = client.get("/api/v1/tactics/puzzles/next").json
    catalog = app.extensions["catalog_tactics"]
    solution = list(catalog.get(payload["puzzle_id"]).solution_moves_uci)
    # Insert `mistakes` wrong-but-legal moves before the real first move.
    for _ in range(mistakes):
        correct_uci = solution[0]
        wrong = next(
            f"{from_sq}{opt['to']}{opt['promotion'] or ''}"
            for from_sq, options in payload["legal_targets"].items()
            for opt in options
            if f"{from_sq}{opt['to']}{opt['promotion'] or ''}" != correct_uci
        )
        client.post(
            "/api/v1/tactics/moves",
            json={"session_id": payload["session_id"], "uci": wrong},
            headers=HEADERS,
        )
    last = None
    for uci in solution[::2]:
        response = client.post(
            "/api/v1/tactics/moves",
            json={"session_id": payload["session_id"], "uci": uci},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        last = response.json
        if last["completed"]:
            break
    assert last is not None
    return last


def test_batch_records_clean_solves(client, app) -> None:
    last = None
    for _ in range(TACTICS_BATCH_SIZE):
        last = _solve_puzzle(client, app, mistakes=0)
    assert last["batch_completed"] is True
    result = last["batch_result"]
    assert sum(result["per_puzzle_points"]) == result["points_earned"]
    assert result["points_earned"] == result["points_possible"]
    history = client.get("/api/v1/tactics/batches").json
    assert len(history["batches"]) == 1
    assert history["batches"][0]["points_earned"] == result["points_earned"]


def test_batch_records_partial_credit(client, app) -> None:
    for _ in range(TACTICS_BATCH_SIZE):
        last = _solve_puzzle(client, app, mistakes=1)
    assert last["batch_completed"] is True
    result = last["batch_result"]
    # Every puzzle scored half points → total should be roughly half of possible
    # (allowing for rounding across five puzzles).
    assert 0 < result["points_earned"] < result["points_possible"]


def test_batch_records_zero_for_multiple_mistakes(client, app) -> None:
    # One puzzle with 3 mistakes should contribute 0 to the batch.
    first = _solve_puzzle(client, app, mistakes=3)
    assert first.get("puzzle_points") == 0
    # Complete the rest with clean solves.
    for _ in range(TACTICS_BATCH_SIZE - 1):
        _solve_puzzle(client, app, mistakes=0)
    history = client.get("/api/v1/tactics/batches").json["batches"]
    assert history[0]["per_puzzle_points"][0] == 0


def test_next_puzzle_reports_batch_progress(client) -> None:
    payload = client.get("/api/v1/tactics/puzzles/next").json
    assert payload["batch"]["index"] == 0
    assert payload["batch"]["puzzles_played"] == 0
    assert payload["batch"]["points_earned"] == 0
    assert payload["batch"]["batch_size"] == TACTICS_BATCH_SIZE


def test_reveal_records_zero_points_and_returns_full_solution(client, app) -> None:
    new = client.get("/api/v1/tactics/puzzles/next").json
    catalog = app.extensions["catalog_tactics"]
    puzzle = catalog.get(new["puzzle_id"])
    solution_len = len(puzzle.solution_moves_uci)
    response = client.post(
        "/api/v1/tactics/reveal",
        json={"session_id": new["session_id"]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json
    assert body["given_up"] is True
    assert body["completed"] is True
    assert body["puzzle_points"] == 0
    assert body["point_awarded"] is False
    assert body["expected_moves_san"]
    assert len(body["fen_sequence"]) == solution_len + 1
    assert body["fen_sequence"][0] == puzzle.presented_fen
    # Batch progress advanced by one puzzle even though it was a give-up.
    assert body["batch"]["puzzles_played"] == 1


def test_reveal_stale_session_returns_404(client) -> None:
    response = client.post(
        "/api/v1/tactics/reveal",
        json={"session_id": "no-such"},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_reveal_endpoint_rejects_cross_origin(client) -> None:
    assert (
        client.post(
            "/api/v1/tactics/reveal",
            json={"session_id": "x"},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )


def test_stats_page_and_endpoint_available(client) -> None:
    page = client.get("/tactics/stats")
    assert page.status_code == 200
    endpoint = client.get("/api/v1/tactics/batches")
    assert endpoint.status_code == 200
    assert endpoint.json["batches"] == []
    assert endpoint.json["statistics"]["batches"] == 0
