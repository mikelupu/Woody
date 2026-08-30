from __future__ import annotations

import csv
from pathlib import Path

import pytest

from hanging_piece_trainer.app import create_app
from hanging_piece_trainer.lichess_index import LichessIndex, SearchQuery
from hanging_piece_trainer.search import SearchError, query_from_payload, save_search_as_package

HEADERS = {"Origin": "http://localhost"}


# A tiny handful of real-looking Lichess puzzle rows.
FIXTURE_ROWS = [
    (
        "p001",
        "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 3",
        "e1g1 g8f6",
        "1200",
        "80",
        "60",
        "800",
        "fork middlegame short",
        "https://lichess.org/x",
        "",
        "",
    ),
    (
        "p002",
        "rnbqkbnr/ppp2ppp/8/3pp3/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 3",
        "e4d5 e5e4",
        "1300",
        "85",
        "70",
        "900",
        "fork middlegame short",
        "https://lichess.org/y",
        "",
        "",
    ),
    (
        "p003",
        "rnbqkb1r/pp2pppp/2p2n2/3p4/2P5/5NP1/PP1PPP1P/RNBQKB1R w KQkq - 0 4",
        "c4d5 c6d5",
        "1400",
        "75",
        "80",
        "1200",
        "fork pin middlegame short",
        "https://lichess.org/z",
        "",
        "",
    ),
    (
        "p004",
        "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
        "e1g1 f8c5",
        "1250",
        "82",
        "65",
        "700",
        "fork middlegame short",
        "https://lichess.org/w",
        "",
        "",
    ),
    (
        "p005",
        "rnbqkbnr/ppp1pppp/8/3p4/8/4PN2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
        "f1b5 c8d7",
        "1350",
        "78",
        "75",
        "1000",
        "fork opening short",
        "https://lichess.org/v",
        "Sicilian_Defense",
        "",
    ),
    (
        "p006",
        "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
        "g8f6 e1g1",
        "1150",
        "88",
        "55",
        "600",
        "fork middlegame short",
        "https://lichess.org/u",
        "",
        "",
    ),
    (
        "p007",
        "rnbqkbnr/pp3ppp/8/2ppp3/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 4",
        "e4d5 c6d5",
        "1450",
        "72",
        "85",
        "1300",
        "fork middlegame short",
        "https://lichess.org/t",
        "",
        "",
    ),
    (
        "p008",
        "rnbqkb1r/pp2pppp/2p2n2/3p4/2P5/5NP1/PP1PPP1P/RNBQKB1R b KQkq - 0 4",
        "d5c4 e2e4",
        "1200",
        "90",
        "60",
        "750",
        "fork middlegame short",
        "https://lichess.org/s",
        "",
        "",
    ),
    (
        "p009",
        "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
        "d7d6 d2d3",
        "1050",
        "92",
        "50",
        "500",
        "fork middlegame short",
        "https://lichess.org/r",
        "",
        "",
    ),
    (
        "p010",
        "rnbqkbnr/ppp1pppp/8/3p4/8/4PN2/PPPP1PPP/RNBQKB1R b KQkq - 0 3",
        "b8c6 f1e2",
        "1500",
        "70",
        "90",
        "1500",
        "fork opening short",
        "https://lichess.org/q",
        "",
        "",
    ),
    (
        "p011",
        "rnbqkbnr/ppp2ppp/8/3pp3/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 3",
        "c3d5 f8b4",
        "1100",
        "88",
        "60",
        "700",
        "pin middlegame short",
        "https://lichess.org/pp",
        "",
        "",
    ),
    (
        "p012",
        "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 3",
        "b1c3 f8c5",
        "1250",
        "80",
        "70",
        "800",
        "pin opening short",
        "https://lichess.org/oo",
        "",
        "",
    ),
    (
        "p013",
        "rnbqkbnr/ppp1pppp/8/3p4/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 2",
        "e4d5 c7c6",
        "1400",
        "78",
        "80",
        "1100",
        "fork middlegame short",
        "https://lichess.org/nn",
        "",
        "",
    ),
    (
        "p014",
        "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
        "b1c3 g8f6",
        "1180",
        "84",
        "62",
        "820",
        "fork middlegame short",
        "https://lichess.org/mm",
        "",
        "",
    ),
    (
        "p015",
        "rnbqkbnr/ppp2ppp/8/3pp3/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 3",
        "d2d3 g8f6",
        "1320",
        "77",
        "72",
        "950",
        "fork middlegame short",
        "https://lichess.org/ll",
        "",
        "",
    ),
]


@pytest.fixture()
def fixture_csv(tmp_path: Path) -> Path:
    path = tmp_path / "lichess.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "PuzzleId",
                "FEN",
                "Moves",
                "Rating",
                "RatingDeviation",
                "Popularity",
                "NbPlays",
                "Themes",
                "GameUrl",
                "OpeningTags",
                "DailyDate",
            ]
        )
        w.writerows(FIXTURE_ROWS)
    return path


@pytest.fixture()
def index(tmp_path: Path, fixture_csv: Path) -> LichessIndex:
    idx = LichessIndex(tmp_path / "idx.sqlite3", source_path=fixture_csv)
    idx.build()
    return idx


def test_index_status_reports_ready(index: LichessIndex) -> None:
    status = index.status()
    assert status["state"] == "ready"
    assert status["count"] == len(FIXTURE_ROWS)
    assert status["source_available"] is True


def test_preview_counts_and_filters(index: LichessIndex) -> None:
    fork_preview = index.preview(SearchQuery(required_themes=("fork",)))
    assert fork_preview.count == 13  # fork rows in fixture
    pin_preview = index.preview(SearchQuery(required_themes=("pin",)))
    assert pin_preview.count == 3  # p003, p011, p012
    combined = index.preview(SearchQuery(required_themes=("fork", "pin")))
    assert combined.count == 1  # only p003 has both


def test_preview_ranges_and_side_to_move(index: LichessIndex) -> None:
    whites = index.preview(SearchQuery(side_to_move="white"))
    blacks = index.preview(SearchQuery(side_to_move="black"))
    assert whites.count + blacks.count == len(FIXTURE_ROWS)


def test_preview_phase_and_mate_in(index: LichessIndex) -> None:
    opening = index.preview(SearchQuery(phase="opening"))
    assert opening.count == 3  # p005, p010, p012
    middlegame = index.preview(SearchQuery(phase="middlegame"))
    assert middlegame.count == 12  # all except opening


def test_matching_ids_ranked_is_deterministic(index: LichessIndex) -> None:
    r1 = index.matching_ids_ranked(SearchQuery(required_themes=("fork",), seed=1), limit=5)
    r2 = index.matching_ids_ranked(SearchQuery(required_themes=("fork",), seed=1), limit=5)
    assert [row["id"] for row in r1] == [row["id"] for row in r2]
    # Different seed → different order
    r3 = index.matching_ids_ranked(SearchQuery(required_themes=("fork",), seed=2), limit=5)
    assert [row["id"] for row in r1] != [row["id"] for row in r3]


def test_save_search_as_package_writes_catalog(tmp_path: Path, index: LichessIndex) -> None:
    output_dir = tmp_path / "packages"
    query = SearchQuery(required_themes=("fork",), target_count=10, seed=42)
    path, catalog = save_search_as_package(
        index,
        query=query,
        slug="my-forks",
        title="My Forks",
        description="Testing",
        existing_slugs=set(),
        output_dir=output_dir,
    )
    assert path.exists()
    assert path.name == "my-forks.json"
    assert catalog.slug == "my-forks"
    assert catalog.package["kind"] == "user"
    assert catalog.package["description"] == "Testing"
    assert catalog.package["query"]["required_themes"] == ["fork"]
    assert catalog.target_count == 10


def test_save_rejects_bad_target_count(tmp_path: Path, index: LichessIndex) -> None:
    with pytest.raises(SearchError) as exc_info:
        save_search_as_package(
            index,
            query=SearchQuery(required_themes=("fork",), target_count=7),
            slug="bad-count",
            title="Bad",
            description="",
            existing_slugs=set(),
            output_dir=tmp_path / "pkgs",
        )
    assert exc_info.value.code == "invalid_count"


def test_save_rejects_slug_in_use(tmp_path: Path, index: LichessIndex) -> None:
    with pytest.raises(SearchError) as exc_info:
        save_search_as_package(
            index,
            query=SearchQuery(required_themes=("fork",), target_count=10),
            slug="taken",
            title="Taken",
            description="",
            existing_slugs={"taken"},
            output_dir=tmp_path / "pkgs",
        )
    assert exc_info.value.code == "slug_in_use"


def test_query_from_payload_parses_and_validates() -> None:
    q = query_from_payload(
        {
            "required_themes": "fork,middlegame",
            "any_of_themes": ["pin"],
            "rating_min": 1200,
            "rating_max": "1500",
            "phase": "middlegame",
            "target_count": 20,
        }
    )
    assert q.required_themes == ("fork", "middlegame")
    assert q.any_of_themes == ("pin",)
    assert q.rating_min == 1200
    assert q.rating_max == 1500
    assert q.phase == "middlegame"
    assert q.target_count == 20


def test_query_from_payload_rejects_bad_phase() -> None:
    with pytest.raises(SearchError):
        query_from_payload({"phase": "not-a-phase"})


def test_app_preview_endpoint(tmp_path: Path, fixture_csv: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    app.extensions["lichess_index"].build()
    client = app.test_client()

    r = client.post(
        "/api/v1/tactics/search/preview",
        json={"required_themes": "fork"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json["count"] == 13
    assert len(r.json["sample"]) > 0


def test_app_save_and_delete_package(tmp_path: Path, fixture_csv: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    app.extensions["lichess_index"].build()
    client = app.test_client()

    r = client.post(
        "/api/v1/tactics/packages",
        json={
            "query": {
                "required_themes": "fork",
                "target_count": 10,
                "seed": 42,
            },
            "package": {
                "slug": "my-forks",
                "title": "My Forks",
                "description": "",
            },
        },
        headers=HEADERS,
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.json["slug"] == "my-forks"
    assert r.json["count"] == 10

    # New package appears in the picker.
    listing = client.get("/api/v1/tactics/packages").json
    slugs = [p["slug"] for p in listing["packages"]]
    assert "my-forks" in slugs

    # It's playable.
    play = client.get("/api/v1/tactics/my-forks/puzzles/next")
    assert play.status_code == 200

    # It's deletable.
    d = client.delete("/api/v1/tactics/packages/my-forks", headers=HEADERS)
    assert d.status_code == 200
    assert d.json == {"slug": "my-forks", "deleted": True}
    listing2 = client.get("/api/v1/tactics/packages").json
    assert "my-forks" not in [p["slug"] for p in listing2["packages"]]


def test_curated_packages_cannot_be_deleted(client_and_app) -> None:
    client, _app = client_and_app
    r = client.delete("/api/v1/tactics/packages/tri-band-tactics", headers=HEADERS)
    assert r.status_code == 403


def test_slug_in_use_returns_conflict(tmp_path: Path, fixture_csv: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    app.extensions["lichess_index"].build()
    client = app.test_client()
    body = {
        "query": {"required_themes": "fork", "target_count": 10, "seed": 42},
        "package": {"slug": "dupes", "title": "First", "description": ""},
    }
    assert client.post("/api/v1/tactics/packages", json=body, headers=HEADERS).status_code == 201
    dupe = client.post("/api/v1/tactics/packages", json=body, headers=HEADERS)
    assert dupe.status_code == 409
    assert dupe.json["error"]["code"] == "slug_in_use"


@pytest.fixture()
def client_and_app(tmp_path: Path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
        }
    )
    return app.test_client(), app


def test_preview_batch_flow(tmp_path: Path, fixture_csv: Path) -> None:
    """The Try-these-10 flow: build a batch, walk its puzzles as sessions,
    without persisting anything to the tactics history."""
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    app.extensions["lichess_index"].build()
    client = app.test_client()

    # Sample up to 10 puzzle rows from the current query.
    created = client.post(
        "/api/v1/tactics/preview/batch",
        json={"required_themes": "fork"},
        headers=HEADERS,
    )
    assert created.status_code == 200
    body = created.json
    assert body["batch_id"]
    assert 0 < body["count"] <= 10
    assert len(body["puzzle_ids"]) == body["count"]
    batch_id = body["batch_id"]
    total = body["count"]

    # Batch page renders tactics.html tagged with the batch id.
    page = client.get(f"/tactics/preview/batch/{batch_id}")
    assert page.status_code == 200
    assert f'data-preview-batch="{batch_id}"'.encode() in page.data

    # Metadata endpoint returns the same ids for page bootstrap.
    meta = client.get(f"/api/v1/tactics/preview/batch/{batch_id}")
    assert meta.status_code == 200
    assert meta.json["puzzle_ids"] == body["puzzle_ids"]

    # Walk through every puzzle in the batch via the start-by-index endpoint.
    for index in range(total):
        started = client.post(
            f"/api/v1/tactics/preview/batch/{batch_id}/start",
            json={"index": index},
            headers=HEADERS,
        )
        assert started.status_code == 200, started.get_data(as_text=True)
        payload = started.json
        assert payload["batch_index"] == index
        assert payload["batch_total"] == total
        assert payload["session_id"]

    # No DB writes happened.
    stats = client.get("/api/v1/tactics/tri-band-tactics/stats").json
    assert stats["attempts"] == 0


def test_preview_batch_rejects_out_of_range_and_stale(tmp_path: Path, fixture_csv: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    app.extensions["lichess_index"].build()
    client = app.test_client()

    created = client.post(
        "/api/v1/tactics/preview/batch",
        json={"required_themes": "fork"},
        headers=HEADERS,
    )
    batch_id = created.json["batch_id"]

    bad_index = client.post(
        f"/api/v1/tactics/preview/batch/{batch_id}/start",
        json={"index": 999},
        headers=HEADERS,
    )
    assert bad_index.status_code == 400
    assert bad_index.json["error"]["code"] == "index_out_of_range"

    stale = client.post(
        "/api/v1/tactics/preview/batch/no-such-batch/start",
        json={"index": 0},
        headers=HEADERS,
    )
    assert stale.status_code == 404
    assert stale.json["error"]["code"] == "stale_batch"


def test_opening_tags_endpoint_lists_distinct_sorted_tags(
    tmp_path: Path, fixture_csv: Path
) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    # Not yet built → 409.
    client = app.test_client()
    assert client.get("/api/v1/tactics/search/opening-tags").status_code == 409

    app.extensions["lichess_index"].build()
    r = client.get("/api/v1/tactics/search/opening-tags")
    assert r.status_code == 200
    tags = r.json["opening_tags"]
    assert tags == sorted(tags), "expected sorted output"
    assert len(tags) == len(set(tags)), "expected distinct tags"
    # Fixture only tags p005 with `Sicilian_Defense`.
    assert "Sicilian_Defense" in tags


def test_preview_batch_rejects_zero_matches(tmp_path: Path, fixture_csv: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    app.extensions["lichess_index"].build()
    client = app.test_client()

    r = client.post(
        "/api/v1/tactics/preview/batch",
        json={"required_themes": "no-such-theme"},
        headers=HEADERS,
    )
    assert r.status_code == 409
    assert r.json["error"]["code"] == "no_matches"


def test_preview_start_requires_index(tmp_path: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(tmp_path / "missing.zst"),
        }
    )
    client = app.test_client()
    r = client.post(
        "/api/v1/tactics/preview/start",
        json={"puzzle_id": "p001"},
        headers=HEADERS,
    )
    assert r.status_code == 409
    assert r.json["error"]["code"] == "index_not_ready"


def test_preview_start_unknown_puzzle_returns_404(tmp_path: Path, fixture_csv: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "progress.sqlite3"),
            "USER_PACKAGES_DIR": str(tmp_path / "packages"),
            "LICHESS_INDEX_PATH": str(tmp_path / "idx.sqlite3"),
            "LICHESS_SOURCE_PATH": str(fixture_csv),
        }
    )
    app.extensions["lichess_index"].build()
    client = app.test_client()
    r = client.post(
        "/api/v1/tactics/preview/start",
        json={"puzzle_id": "does-not-exist"},
        headers=HEADERS,
    )
    assert r.status_code == 404
    assert r.json["error"]["code"] == "unknown_puzzle"
