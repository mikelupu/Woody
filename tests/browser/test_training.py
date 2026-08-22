from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from hanging_piece_trainer.app import create_app

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1",
    reason="run with `make browser-test` after `make browser-setup`",
)


@pytest.fixture(scope="module")
def live_app(tmp_path_factory: pytest.TempPathFactory):
    root: Path = tmp_path_factory.mktemp("browser-progress")
    app = create_app({"TESTING": True, "DATABASE": str(root / "progress.sqlite3")})
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_complete_keyboard_accessible_training_flow(live_app: str) -> None:
    off_origin_requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on(
            "request",
            lambda request: (
                off_origin_requests.append(request.url)
                if not request.url.startswith(live_app)
                else None
            ),
        )
        page.goto(live_app)
        page.get_by_role("heading", name="Hanging Piece Trainer").wait_for()
        squares = page.get_by_role("gridcell")
        assert squares.count() == 64
        assert all(squares.nth(index).get_attribute("aria-label") for index in range(64))

        page.get_by_role("button", name="Both").click()
        assert page.get_by_role("button", name="Both").get_attribute("aria-pressed") == "true"
        eligible = page.locator(".square:not([disabled])").first
        eligible.click()
        square = eligible.get_attribute("data-square")
        assert square
        assert page.locator(f'[data-square="{square}"]').evaluate(
            "element => element.classList.contains('hanging')"
        )

        page.get_by_role("button", name="Check answer").click()
        page.get_by_role("heading", name="Review").wait_for()
        assert page.locator("#attempts").text_content() == "1"
        assert page.locator("#history tr").count() >= 1
        page.get_by_role("button", name="Next puzzle").click()
        page.locator("#board-status").get_by_text(
            "Select every hanging piece", exact=False
        ).wait_for()
        assert (
            page.get_by_role("button", name="Side to move").get_attribute("aria-pressed") == "true"
        )
        assert off_origin_requests == []
        browser.close()
