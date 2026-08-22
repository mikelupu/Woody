# Hanging Piece Trainer

A private, offline browser trainer for recognizing hanging chess pieces. It serves a
single-user Flask application on loopback, keeps expected answers on the backend until submission,
and stores progress in a local append-only SQLite ledger.

## Install and run

Requirements: Python 3.13+, [`uv`](https://docs.astral.sh/uv/), Make, and a modern desktop browser.

```sh
make setup
make run
```

Open <http://127.0.0.1:5000> and stop the application with `Ctrl+C`. The normal command binds only to
`127.0.0.1`, keeps Flask debug mode off, serves all assets locally, and makes no runtime network
requests. `make dev` enables reloading for development but remains loopback-only.

## Training workflow

Each position is oriented with the side to move at the bottom. Choose one scope:

- **Side to move** (the default on every new puzzle)
- **White**
- **Black**
- **Both**

Select every **Hanging** piece: one that is attacked and has no friendly geometric defender. Pinned
pieces still attack and defend geometrically. Undefended status is calculated internally but does
not require a separate user selection.

Scoring awards one point only when the submitted hanging set is exactly correct. There is no timing
bonus or target. After a committed answer, green ticks mark correct selections, purple dashed
outlines mark misses, and red crosses mark incorrect extras. The review panel provides equivalent
text. Squares, scopes, categories, submission, and navigation are keyboard-operable; arrow keys move
focus across the board.

## Progress and recovery

The progress database defaults to `instance/progress.sqlite3` under the directory where the app is
started. Set `HPT_INSTANCE_PATH` to use another local directory.

To back up or restore progress:

1. Stop the application.
2. Copy `instance/progress.sqlite3` and retain the original until the restored copy has been tested.
3. Restart the application and check `/api/v1/health`.

To explicitly reset progress, stop the app and move—not silently delete—the database aside, then
restart. A corrupt database or unsupported schema stops progress initialization and is never
automatically replaced. Restore a known-good copy or explicitly move the damaged file aside.

## Development and verification

```sh
make install          # runtime dependencies
make setup            # all development/curation/browser-test dependencies
make check            # lint + tests
make test-cov         # branch coverage; minimum 80%
make catalog-validate # reconstruct and recompute all 100 bundled positions
make browser-setup    # one-time Chromium install for browser acceptance
make browser-test     # real Flask + Chromium workflow and network allowlist
make catalog-import   # stream the locally stored official Lichess snapshot
```

The JSON API is under `/api/v1`: `GET /puzzles/next`, `POST /attempts`, `GET /stats`,
`GET /attempts`, and `GET /health`. Attempt writes require same-origin JSON and a client-generated
idempotency key. The submission contains only the selected hanging squares; public puzzle responses
never contain expected answers. The exercise header displays the catalog puzzle ID and identifies it
as a Lichess puzzle ID when the catalog record has Lichess provenance.

## Catalog curation

The committed catalog contains 100 deterministically selected positions from the official Lichess
puzzle snapshot stored at `data/source/lichess_db_puzzle.csv.zst`. The source archive remains local
and excluded from version control; its SHA-256 and URL are embedded in the generated catalog. To
rebuild or refresh the catalog from that snapshot:

```sh
uv run hpt-curate build /path/to/lichess_db_puzzle.csv.zst \
  src/hanging_piece_trainer/data/puzzles.json \
  --seed 20260809 \
  --source-url https://database.lichess.org/lichess_db_puzzle.csv.zst \
  --expected-source-sha256 a0ea9129c6b6434dfb34a9ac4ec660c9cfff22b2de465e01854f018fc847f073

make catalog-validate
```

The curation command streams input, requires the exact `middlegame` theme token, applies the first
UCI move, requires at least one side-to-move hanging piece, performs deterministic bounded-memory
sampling, stores source and catalog checksums, and atomically refuses to replace a valid catalog
when fewer than 100 records qualify. The official archive is stored locally at
`data/source/lichess_db_puzzle.csv.zst` and intentionally excluded from version control. The
selection algorithm hash-ranks puzzle IDs using the seed and retains the 100 lowest-ranked eligible
positions, so identical source, rules, and seed inputs produce the same catalog.

## Scope and limitations

This is a desktop-first, single-user local application. It does not move chess pieces, solve the
source tactic, use an engine, provide accounts/cloud sync, expose a LAN server, perform telemetry,
or optimize training adaptively. See [the technical blueprint](design/blueprint.md) for the complete
architecture and [provenance](PROVENANCE.md) for dependency/data origins.
