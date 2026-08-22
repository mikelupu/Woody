.PHONY: setup install run dev check fix lint format test test-cov browser-setup browser-test catalog-import catalog-validate catalog-tactics

setup:
	uv sync --all-extras
	@if [ -d .git ]; then uv run pre-commit install; else echo "No .git directory; skipping hook installation"; fi

install:
	uv sync

run:
	uv run hanging-piece-trainer

dev:
	uv run flask --app hanging_piece_trainer.app:create_app run --debug --host 127.0.0.1

check: lint test

fix:
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

test:
	uv run pytest

test-cov:
	uv run coverage run -m pytest
	uv run coverage report

browser-setup:
	uv run playwright install chromium

browser-test:
	RUN_BROWSER_TESTS=1 uv run pytest tests/browser

catalog-import:
	uv run hpt-curate build data/source/lichess_db_puzzle.csv.zst src/hanging_piece_trainer/data/puzzles.json \
		--seed 20260809 \
		--source-name lichess_db_puzzle.csv.zst \
		--source-url https://database.lichess.org/lichess_db_puzzle.csv.zst \
		--expected-source-sha256 a0ea9129c6b6434dfb34a9ac4ec660c9cfff22b2de465e01854f018fc847f073 \
		--progress-every 250000

catalog-validate:
	uv run python -m hanging_piece_trainer.curation validate src/hanging_piece_trainer/data/puzzles.json

catalog-tactics:
	uv run python scripts/curate_tactics.py data/source/lichess_db_puzzle.csv.zst \
		src/hanging_piece_trainer/data/puzzles_tactics.json \
		--seed 20260820 \
		--source-name lichess_db_puzzle.csv.zst \
		--source-url https://database.lichess.org/lichess_db_puzzle.csv.zst \
		--progress-every 250000
