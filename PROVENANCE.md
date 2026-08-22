# Provenance and licenses

## Runtime

- Flask — local HTTP, templates, static assets, and JSON; BSD-3-Clause.
- python-chess / chess — FEN, UCI, legal moves, and geometric attack maps; GPL-3.0-or-later.
- Python `sqlite3` — local transactional progress storage; Python standard library.

Exact resolved versions are recorded in `uv.lock`. No JavaScript packages, remote fonts, CDNs,
analytics, or telemetry are used at runtime. Chess pieces use operating-system Unicode glyphs.

## Development and curation

- pytest, coverage, Ruff, and pre-commit provide automated verification and quality checks.
- Playwright Python is declared for browser acceptance automation.
- zstandard streams optional `.zst` Lichess source snapshots.

Refer to each locked package distribution for its authoritative license text.

## Puzzle data

The bundled `puzzles.json` contains 100 positions selected from the official Lichess open puzzle
database snapshot updated on 2026-08-02. The locally stored compressed source is 304,384,407 bytes
and has SHA-256 `a0ea9129c6b6434dfb34a9ac4ec660c9cfff22b2de465e01854f018fc847f073`,
matching Lichess's published checksum. Lichess database exports are released under CC0.

Catalog metadata records the source URL/checksum, selection seed, rules version, and catalog
checksum. `scripts/generate_development_catalog.py` remains available only as an offline fallback;
it is not the source of the shipped catalog.
