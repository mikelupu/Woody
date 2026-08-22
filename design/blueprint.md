---
id: hanging-piece-trainer
title: Hanging Piece Trainer
status: Implemented; browser acceptance pending
created: 2026-08-09
author: Michael Farrugia
related_prd: not bundled in this repository
related_epic: none
---

# Hanging Piece Trainer - Technical Blueprint (HLD)

> **Implemented product simplification (2026-08-10):** The training UI and attempt API collect only
> hanging-piece selections. Undefended classification remains an internal rule used to determine
> whether a piece is hanging. This note supersedes the dual-category browser and request details
> retained below as historical design context.

## Executive Summary

Hanging Piece Trainer will be a single-process local web application with a Python backend and a
small browser frontend. Flask will serve a Jinja-rendered application shell, local JavaScript and
CSS, and a narrow JSON API. A custom accessible 8×8 button grid will render the chessboard because
the product selects pieces but never moves them. This avoids a frontend framework, Node build
pipeline, and general-purpose chessboard dependency while retaining explicit control over the
required White, Black, Both, and Side-to-move selection modes and review markers.

`python-chess` will own position reconstruction and pin-agnostic attack-map calculations. A
build-time curation tool will convert a Lichess puzzle snapshot into an immutable, versioned catalog
of exactly 100 validated positions. The catalog will remain private to the backend so expected
answers are not sent before submission. SQLite, accessed through Python's standard `sqlite3`
module, will persist append-only attempts; score and other statistics will be derived from those
attempts. The runtime will bind only to the loopback interface and will make no external requests.

## Business Context Reference

**PRD Reference**: The upstream Hanging Piece Trainer PRD used to prepare this blueprint is not
bundled in this repository. Its product requirements and acceptance boundaries are preserved in
this blueprint and the implementation tickets.

The PRD is the authority for product goals, user stories, classification definitions, scope, and
acceptance criteria. This blueprint translates those requirements into technical boundaries and
delivery phases.

## Context

### Business Context

- **Problem**: The user wants focused practice recognizing undefended and hanging pieces before
  those oversights become chess blunders.
- **Impact**: A single chess learner receives repeatable, private, local training with visual
  correction and persistent progress.
- **Success Metrics**: Exactly 100 valid positions, deterministic classifications, complete visual
  feedback, correct score/streak behavior, persistent history, and all P0 UAT scenarios passing.

### Technical Context

- **Current State**: The repository is greenfield. It contains an approved PRD and architecture
  scaffolding but no application code, dependency manifests, tests, or ADRs.
- **Constraints**: Python 3.13+, `uv` dependency management, `make` task entrypoints, local/offline
  runtime, one user, no login, no telemetry, no runtime third-party assets, and no quantitative
  delivery or response-time requirements.
- **Dependencies**: Lichess puzzle data is a build-time source only. Flask and `python-chess` are
  runtime packages; SQLite is provided by Python. Browser automation is a development dependency.
- **Workload**: One local user, 100 bundled puzzles, and a small append-only attempt history.

### Source Documents Reviewed

- Approved Hanging Piece Trainer PRD.
- Repository architecture overview and artifact conventions.
- Repository Python, `uv`, Make, Ruff, pre-commit, and pytest rules.
- Official Flask, Python `sqlite3`, `python-chess`, and Lichess puzzle-format documentation.
- Three parallel read-only repository investigations covering architecture, Python/rules, and
  frontend/persistence concerns.

## Goals and Non-Goals

### Goals

- Provide a locally served browser experience backed by Python.
- Reconstruct and validate exactly 100 Lichess middlegame positions deterministically.
- Calculate undefended and hanging pieces for White and Black under the PRD's pin-agnostic rules.
- Support Side to move, White, Black, and Both classification scopes, defaulting per puzzle to Side
  to move while keeping board orientation tied to the actual side to move.
- Keep expected answers server-side until an answer is submitted.
- Render correct answers with positive ticks, misses with a dedicated color highlight, and incorrect
  extras with a distinct negative marker, with equivalent text.
- Commit each submission and its score/streak effect atomically to local SQLite storage.
- Derive all statistics from the append-only attempt ledger.
- Preserve modular boundaries that allow later puzzle sets or training modes.

### Non-Goals

- Moving chess pieces, solving the original tactic, engine evaluation, or pin-aware analysis.
- Accounts, authentication, authorization roles, cloud synchronization, or multi-user concurrency.
- Live Lichess API/database access during application runtime.
- React, Vue, another SPA framework, or a Node-based production build pipeline.
- A general-purpose chessboard widget or drag-and-drop move system.
- Timed scoring, speed targets, SLAs, or quantitative response-time requirements.
- Mobile-specific layout optimization, advanced analytics, or adaptive training.

## Architecture Overview

### High-Level Design

```text
Build time
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
│ Lichess CSV.zst  │───▶│ Curation command │───▶│ Versioned puzzles.json│
└──────────────────┘    │ + python-chess   │    │ (100 positions)      │
                        └──────────────────┘    └──────────┬───────────┘
                                                         │ read-only
Runtime                                                   ▼
┌────────────────────┐  local HTTP  ┌──────────────────────────────────┐
│ Browser UI         │◀────────────▶│ Flask application               │
│ Jinja + JS + CSS   │              │ puzzle/training services        │
│ accessible board   │              │ python-chess rule adapter       │
└────────────────────┘              └──────────────┬───────────────────┘
                                                  │ transactions
                                                  ▼
                                      ┌────────────────────────┐
                                      │ progress.sqlite3       │
                                      │ append-only attempts   │
                                      └────────────────────────┘
```

### Key Components

1. **Curation Pipeline**: Streams Lichess puzzle records, reconstructs presented positions,
   computes classifications, and emits a deterministic catalog.
2. **Puzzle Catalog**: Loads and validates immutable puzzle content without exposing expected
   answers before submission.
3. **Training Service**: Resolves classification scope, verifies selections, calculates score and
   feedback, and coordinates durable attempt commits.
4. **Progress Repository**: Owns SQLite schema, transactions, idempotency, attempt history, and
   aggregate queries.
5. **Flask Web Layer**: Serves the shell/assets and maps JSON requests to application services.
6. **Browser Training UI**: Owns provisional selection state, board rendering, result overlays,
   navigation, and accessible text output.

### System Interactions

#### Load and classify

1. The browser requests the application shell and then a puzzle.
2. The backend selects a puzzle and returns public metadata, presented FEN, side to move, and a
   unique presentation identifier; expected classifications are omitted.
3. The browser orients the board to the side to move and initializes scope to `side_to_move`.
4. The user may switch to `white`, `black`, or `both`; orientation does not change.
5. The UI accepts only non-king pieces eligible under the active scope.

#### Submit and review

1. The browser sends the presentation identifier, scope, selected undefended/hanging squares,
   client-generated attempt identifier, and informational completion duration.
2. The training service resolves the effective color set and obtains expected classifications from
   the private catalog.
3. It computes correct, missed, and incorrect sets for both categories and determines exact hanging
   set correctness.
4. The progress repository inserts the attempt in one transaction. A repeated attempt identifier
   returns the original committed result rather than adding another attempt.
5. Only after commit succeeds does the backend return the full review result and updated statistics.
6. The board places positive ticks on correct pieces, miss-color highlights on missed pieces, and
   negative markers on incorrect extras; the feedback panel renders equivalent text.
7. If persistence fails, the backend returns an error without an attempt, and the UI preserves the
   editable provisional answer.

### Data Flow and Trust Boundaries

- Lichess input is untrusted build-time data and must pass schema, move, legality, theme, uniqueness,
  and classification validation.
- Catalog answers are trusted only after deterministic generation and startup/test validation.
- Browser submissions are untrusted. The backend validates scope, presentation identity, squares,
  set relationships, and value bounds, then recomputes results.
- SQLite is the sole authority for committed attempts. Browser memory never independently advances
  score, streak, or history.
- Aggregate statistics are derived, not stored as a second source of truth.

## Technology Stack

| Layer | Selection | Rationale |
|---|---|---|
| Runtime | Python 3.13+ managed by `uv` | Repository standard and user requirement |
| Web | Flask with Jinja | Minimal local server with native templates, static files, JSON responses, and test client |
| Frontend | Semantic HTML, modular vanilla JavaScript, CSS | Sufficient interaction without SPA/build complexity |
| Chess rules | `python-chess` | FEN/UCI support and attack APIs that count pinned pieces as attackers |
| Puzzle content | Versioned JSON catalog | Reviewable immutable artifact; independent from mutable progress |
| Persistence | SQLite via standard `sqlite3` | Transactional local storage without another service or ORM |
| Unit/integration tests | pytest | Repository standard |
| Browser tests | Python Playwright integration | Verifies board interaction, accessibility, persistence, and offline behavior |
| Quality | Ruff, pre-commit, coverage, Make targets | Repository standards and consistent developer entrypoints |

## Architectural Principles

- **One authority per fact**: catalog owns expected answers; SQLite attempts own progress; aggregates
  are derived.
- **Server-authoritative verification**: never trust browser-computed correctness or score.
- **No answer leakage**: public puzzle responses exclude expected classifications.
- **Local by construction**: bind to `127.0.0.1`; bundle all runtime assets; configure no CORS or
  telemetry.
- **Functional core, imperative shell**: chess classification and result comparison remain pure;
  HTTP and SQLite coordinate side effects.
- **Dependency direction**: web and persistence adapters depend on domain/application contracts,
  not the reverse.
- **Minimum sufficient design**: no ORM, SPA framework, cache, background worker, authentication
  layer, or aggregate table for the V1 workload.
- **Repository standards**: apply Y100-SINGLE-RESPONSIBILITY, Y103-DEPENDENCY-INJECTION, avoid
  Z102-GOD-OBJECTS and Z200-LEAKY-ABSTRACTION, and follow the Python standards catalog.

## Major Components

### Component 1: Curation Pipeline

**Purpose**: Produce the fixed, reproducible 100-position training catalog.

**Responsibilities**:

- Accept an explicitly supplied Lichess puzzle snapshot; downloading is a separate operator action.
- Stream compressed or decompressed CSV without retaining the full database in the repository.
- Require standard chess and an exact `middlegame` theme token.
- Parse the source FEN, apply the first UCI move, and validate the resulting position.
- Compute White and Black undefended/hanging sets with the shared rules adapter.
- Retain records whose side-to-move set includes at least one hanging piece.
- Apply a deterministic selection order/seed and emit exactly 100 unique puzzle IDs.
- Store source snapshot metadata, schema version, rules version, provenance URL, and checksum.
- Fail without replacing an existing catalog if fewer than 100 records validate.

**Interfaces**:

- Make/CLI entrypoint taking source path and explicit output path.
- Output: canonical versioned JSON catalog consumed read-only by the application.

**Dependencies**: `python-chess`, CSV/zstd reader, shared domain classification module.

**Scalability Considerations**: Stream input in bounded memory; runtime scale remains exactly 100
catalog entries.

### Component 2: Chess Classification Domain

**Purpose**: Provide deterministic, framework-independent piece-safety classification.

**Responsibilities**:

- Reconstruct a presented board from source FEN and first UCI move.
- Enumerate non-king pieces for either color.
- Count same-color defenders and opposite-color attackers with `python-chess` attack maps.
- Preserve the PRD rule that pinned pieces still attack/defend geometrically.
- Return normalized square sets for `undefended` and `hanging` for White and Black.
- Enforce `hanging ⊆ undefended`.

**Interfaces**:

- Pure domain operations accepting FEN/color and returning immutable classification results.
- No Flask, JSON, SQLite, or catalog-path types cross this boundary.

**Dependencies**: `python-chess` behind a narrow adapter where fixtures can verify library semantics.

**Scalability Considerations**: Constant board size; no caching required.

### Component 3: Puzzle Catalog

**Purpose**: Own immutable puzzle content and answer lookup.

**Responsibilities**:

- Load the bundled JSON catalog once during application creation.
- Validate catalog/schema/rules versions, checksum, uniqueness, count, FEN validity, and answer
  invariants before accepting requests.
- Return answer-free public puzzle views.
- Resolve expected sets for White, Black, Both, or Side to move only during submission.
- Select a next puzzle while avoiding the immediately previous ID.

**Interfaces**:

- `public_puzzle(puzzle_id)` returns safe metadata and presented FEN.
- `expected_answer(puzzle_id, scope)` returns private normalized sets to the training service.

**Dependencies**: Domain value objects and classification validator.

**Scalability Considerations**: In-memory index of 100 records is sufficient.

### Component 4: Training Service

**Purpose**: Coordinate the user-visible training transaction.

**Responsibilities**:

- Create presentation identifiers bound to puzzle identity without exposing answers.
- Validate classification scope and selected squares.
- Normalize `side_to_move` to White or Black while retaining the submitted scope in history.
- Compare expected and submitted sets for each category.
- Calculate positive, missed, and incorrect sets and exact hanging-set score.
- Delegate idempotent attempt commit to the progress repository.
- Return committed review feedback and current derived statistics.

**Interfaces**:

- Application-level commands/queries consumed by Flask routes.
- Injected catalog, progress repository, identifier generator, and clock.

**Dependencies**: Puzzle Catalog and Progress Repository contracts.

**Scalability Considerations**: One local request stream; synchronous execution is sufficient.

### Component 5: Progress Repository

**Purpose**: Persist committed attempts and provide derived history/statistics.

**Responsibilities**:

- Initialize and migrate a versioned SQLite schema.
- Insert one append-only attempt per unique client attempt identifier.
- Commit the complete attempt atomically or roll it back completely.
- Return the existing result for idempotent duplicate submissions.
- Query ordered history and derive total attempts, score, accuracy, current streak, best streak,
  average completion duration, and most recent completion duration.
- Reject unreadable or unsupported schema state without silently recreating progress.

**Interfaces**:

- Repository methods using domain/application attempt records rather than raw route objects.
- Database location supplied by application configuration, defaulting under Flask's local instance
  directory and excluded from version control.

**Dependencies**: Python `sqlite3` only.

**Scalability Considerations**: Serialized local writes are appropriate for one user.

### Component 6: Flask Web Layer

**Purpose**: Expose the local UI and application commands over same-origin HTTP.

**Responsibilities**:

- Construct dependencies through an application factory.
- Serve Jinja templates and locally bundled CSS/JavaScript.
- Expose narrow versioned JSON routes.
- Validate JSON content types and map domain/application failures to stable error responses.
- Enforce loopback defaults, same-origin mutation requests, no CORS, and no external asset URLs.
- Log startup, catalog validation, migration, and unexpected application errors without recording
  full attempt payloads unnecessarily.

**Interfaces**: Browser-facing routes described under API Design.

**Dependencies**: Flask and application services.

**Scalability Considerations**: One synchronous local process; no production orchestration required.

### Component 7: Browser Training UI

**Purpose**: Provide the interactive and accessible training experience.

**Responsibilities**:

- Render an 8×8 semantic button grid from the presented FEN using locally available Unicode chess
  glyphs, coordinates, and accessible piece/square labels.
- Orient the grid to the side to move.
- Offer Side to move, White, Black, and Both scope controls, resetting to Side to move for every
  newly loaded puzzle.
- Maintain provisional undefended/hanging selection sets; selecting hanging also establishes
  undefended, and removing undefended removes hanging.
- When scope changes, remove selections that are no longer eligible while preserving still-eligible
  selections.
- Freeze the answer after committed submission.
- Overlay positive ticks for correct pieces, a configurable dedicated miss-color treatment for
  missed pieces, and a distinct negative marker for incorrect extras.
- Announce equivalent result text containing piece name, color, square, category, and outcome.
- Render statistics and history returned by the backend; never advance them optimistically.

**Interfaces**: Same-origin JSON API and server-rendered shell.

**Dependencies**: Browser DOM, Fetch, CSS; no runtime third-party scripts or assets.

**Scalability Considerations**: Fixed 64-square board and small history views.

## Data Models

### Core Entities

#### PuzzleCatalog

| Field | Purpose |
|---|---|
| `schema_version` | Catalog contract version |
| `rules_version` | Classification semantics version |
| `source` | Lichess snapshot name/date, URL, and checksum |
| `selection_seed` | Reproducible curation input |
| `catalog_checksum` | Detects accidental content changes |
| `puzzles` | Exactly 100 Puzzle records |

#### Puzzle

| Field | Purpose |
|---|---|
| `puzzle_id` | Stable Lichess identity |
| `source_url` | Provenance link |
| `source_fen` / `first_move_uci` | Reconstructable source contract |
| `presented_fen` | Position displayed to the user |
| `side_to_move` | Board orientation and default scope resolution |
| `rating` / `themes` | Retained public context |
| `answers_by_color` | Private White/Black undefended and hanging square sets |

#### Attempt

| Field | Purpose |
|---|---|
| `attempt_id` | Client-generated idempotency key and primary identity |
| `puzzle_id` / `presented_fen` | Exact attempted position |
| `scope` / `effective_colors` | User choice and resolved color set |
| `submitted_undefended` / `submitted_hanging` | Normalized submitted sets |
| `expected_undefended` / `expected_hanging` | Audit snapshot under the attempt's rules version |
| `correct`, `point_awarded` | Exact hanging-set result |
| `completion_ms` | Passive informational measurement; never used for scoring or targets |
| `submitted_at` | UTC commit timestamp |
| `schema_version` / `rules_version` | Future migration and interpretation |

### Relationships and Invariants

- A catalog contains exactly 100 unique puzzles.
- An attempt references one catalog puzzle but retains sufficient answer data for historical audit.
- Hanging sets are subsets of corresponding undefended sets.
- In White/Black modes, submitted and expected squares contain only that color's eligible non-king
  pieces; Both may contain both colors.
- `side_to_move` resolves to exactly one effective color but remains distinguishable in history.
- Score, accuracy, and streaks are pure derivations over committed attempts ordered by commit.
- Attempts are never updated or deleted by the V1 UI.

## API Design

### Browser API

**Base URL**: `/api/v1`

| Method | Endpoint | Purpose | Key behavior |
|---|---|---|---|
| GET | `/puzzles/next` | Load a public puzzle | Omits answers; may accept previous puzzle ID to avoid immediate repeat |
| POST | `/attempts` | Verify and commit an answer | Idempotent by attempt ID; returns review sets only after commit |
| GET | `/stats` | Read aggregate progress | Derived from committed attempts |
| GET | `/attempts` | Read attempt history | Stable newest-first pagination or bounded full V1 list |
| GET | `/health` | Local diagnostic | Reports application/catalog/database readiness without personal data |

Authentication is not required. Mutation requests require same-origin JSON and the application binds
to `127.0.0.1` by default. CORS is disabled. API errors use a stable code, user-safe message, and
retryability indicator; stack traces remain in local development logs only.

### Internal Interfaces

- Web routes exchange request DTOs with the Training Service.
- Training Service consumes catalog and repository protocols injected at application creation.
- Progress Repository alone exchanges SQL with SQLite.
- Domain classification alone exchanges `python-chess` board objects with the library adapter.

## Technical Decisions

### Decision 1: Flask and Server-Rendered Shell

**Decision**: Use Flask/Jinja with modular vanilla JavaScript and CSS.

**Rationale**:

- The product has one focused screen and a small statistics/history view.
- Flask directly supports templates, static assets, JSON responses, and test clients.
- One Python process and one dependency graph reduce setup and offline-delivery complexity.

**Alternatives Considered**:

- **FastAPI + React/Vite**: Strong API typing and component ecosystem, but adds a Node toolchain,
  separate build lifecycle, client routing/state dependencies, and more integration surface.
- **FastAPI + templates/vanilla JS**: Viable, but its async/API strengths are not needed here and
  Flask has a smaller conceptual surface for this synchronous local app.

**Implications**: Frontend contracts need deliberate modularity and DOM-level tests; adding a much
larger client application later may justify revisiting the decision.

**ADR Reference**: Recommended ADR candidate; not yet created.

### Decision 2: Custom Accessible Selection Board

**Decision**: Render an 8×8 semantic button grid rather than adopt a chessboard widget.

**Rationale**:

- V1 selects pieces but never moves them.
- Product-specific overlapping category, eligibility, tick, miss, and negative states are easier to
  express directly than adapt through drag-and-drop overlays.
- Native buttons provide keyboard/focus semantics and accessible labels without another dependency.

**Alternatives Considered**:

- **General chessboard component**: Faster initial piece rendering, but marker/accessibility behavior
  would require a spike and could introduce runtime assets or move-oriented complexity.
- **Canvas/SVG board**: Full visual control, but poorer native semantics and more custom keyboard and
  hit-testing work.

**Implications**: The UI owns board coordinate/orientation rendering; tests must cover all 64-square
mappings for both orientations.

**ADR Reference**: Recommended ADR candidate; not yet created.

### Decision 3: `python-chess` for Pin-Agnostic Attack Maps

**Decision**: Use `python-chess` and its attack/attacker operations, which count pinned pieces as
attackers, behind a domain adapter.

**Rationale**: It directly supports FEN, UCI moves, board validation, and the PRD's geometric rule.

**Alternatives Considered**:

- **Custom chess rules**: Avoids a dependency but creates substantial correctness risk.
- **Browser chess library**: Duplicates rules across languages and weakens backend authority.

**Implications**: Focused fixtures must lock pawn, king, sliding blocker, pinned attacker/defender,
and Both-mode behavior against the PRD rather than blindly trusting library defaults.

**ADR Reference**: Recommended ADR candidate; not yet created.

### Decision 4: Immutable Catalog with Precomputed Answers

**Decision**: Curate a versioned JSON catalog at build time and store expected White/Black sets in
backend-only content.

**Rationale**: It makes the 100-position set reproducible, removes runtime Lichess dependency, keeps
submission work deterministic, and allows review of provenance and rule versions.

**Alternatives Considered**:

- **Compute every answer at submission**: Simple catalog but repeats rule work and makes historical
  answers sensitive to dependency changes.
- **Store puzzles in SQLite with progress**: One file, but mixes immutable shipped data with mutable
  personal state and complicates replacement/recovery boundaries.

**Implications**: Curation and startup validation become mandatory; rules changes require a new
catalog/rules version.

**ADR Reference**: Recommended ADR candidate; not yet created.

### Decision 5: SQLite as the Progress Authority

**Decision**: Persist append-only attempts in backend-managed SQLite and derive aggregates.

**Rationale**: Transactions and idempotent constraints prevent phantom/double attempts, data remains
local, Python includes the driver, and there is no separate service.

**Alternatives Considered**:

- **Browser localStorage**: Persists across sessions but is origin/browser-profile specific, can be
  disabled, and would split verification from durable score authority.
- **JSON progress file**: Human-readable but requires custom locking, atomic replacement, querying,
  and migration behavior already provided by SQLite.

**Implications**: The app must expose the progress-file location and clear recovery errors; no ORM is
necessary for the small explicit schema.

**ADR Reference**: Recommended ADR candidate; not yet created.

### Decision 6: Loopback-Only, Same-Origin Runtime

**Decision**: Bind to `127.0.0.1`, serve all assets locally, disable CORS, and validate Origin and
JSON content type on mutations.

**Rationale**: The product is personal/local, and localhost services should not accept arbitrary
cross-origin writes.

**Alternatives Considered**:

- **LAN binding**: Enables other devices but creates an authentication and network-security scope.
- **Desktop wrapper**: Strong packaging but adds a second runtime/platform layer not required by the
  requested web application.

**Implications**: Remote-device access is explicitly unsupported in V1.

**ADR Reference**: Recommended ADR candidate; not yet created.

## Security Considerations

### Authentication & Authorization

- None for V1 because the server is loopback-only and single-user.
- The application must not bind to all interfaces by default.
- Enabling LAN exposure later requires a new security decision; it is not a configuration toggle in
  V1.

### Data Security

- Progress contains personal performance data but no credentials or regulated PII.
- Data remains in a local SQLite file; no telemetry, CDN, remote font, or analytics requests exist.
- File permissions follow the local operating-system user. Encryption at rest is not required by
  the PRD.
- Expected answers are withheld from API puzzle responses for training integrity, not treated as a
  secret against the machine owner.

### Security Controls

- Bind to loopback, disable CORS, and reject cross-origin mutation requests.
- Require JSON for attempt submission and validate closed enums, square syntax, set sizes, and IDs.
- Use SQL parameter binding and explicit transactions.
- Jinja auto-escaping remains enabled; do not render user-provided HTML.
- Keep debug mode and interactive debugger off in the normal `make run` command.
- Do not log complete answer/history payloads at normal log level.

## Performance & Scalability

### Performance Requirements

The approved PRD defines no quantitative delivery-time, latency, throughput, or response-time
requirements. Correctness, durability, offline operation, and accessible feedback take priority.
Passive completion duration is retained only as a user statistic and does not create a performance
target or affect score.

### Scalability Strategy

- Design for one local user, 100 in-memory puzzle records, and serialized SQLite writes.
- No cache, load balancer, horizontal scaling, distributed session, or database server is needed.
- History queries should use an index on commit order and may add pagination if the ledger grows.

### Monitoring & Observability

- Local structured logs for startup, catalog validation, schema migrations, submission failures,
  and unhandled errors.
- `/health` reports only catalog and database readiness.
- No external metrics, alerts, tracing backend, or telemetry.

## Reliability & Operations

### Error Handling

- Catalog validation failure prevents training and displays a clear local recovery instruction.
- Invalid submissions return a stable client error and do not touch SQLite.
- SQLite submission failures roll back, leave browser selections editable, and do not alter stats.
- Duplicate attempt IDs return the original committed review result.
- Unsupported schema versions stop safely rather than recreating or zeroing progress.
- Browser fetch failures retain the current board and answer until retry or deliberate navigation.

### Deployment Strategy

- Local source installation managed by `uv` and Make.
- `make setup` installs locked dependencies and development tooling.
- `make run` initializes/validates local state and starts Flask on loopback with debug disabled.
- `make dev` may enable reloading for development only.
- Static assets and the curated catalog ship in the repository/package; runtime requires no network.

### Data Recovery

- Document the SQLite path and a safe manual-copy backup procedure while the app is stopped.
- Schema migrations execute transactionally and retain the prior file on failure.
- Corrupt/unsupported files are never silently replaced. The operator may restore a backup or
  explicitly move the file aside to start fresh.
- Formal RPO/RTO targets are not required for this personal application.

## Testing Strategy

### Test Levels

- **Domain unit tests**: FEN reconstruction, attacks/defenders, pins ignored, kings excluded,
  hanging subset invariant, scope resolution, exact-set scoring, and feedback set algebra.
- **Curation tests**: CSV schema, theme token, first-move application, malformed records,
  determinism, uniqueness, count, provenance, checksum, and safe failure.
- **Repository tests**: schema migration, atomic insert, rollback, idempotency, history ordering,
  streak derivation, and corrupt/unsupported schema behavior.
- **Flask integration tests**: answer-free puzzle API, request validation, same-origin mutation,
  commit-before-response, error mapping, and offline asset paths.
- **Browser tests**: both orientations, four scopes/default reset, category-state invariants,
  positive ticks, miss-color highlights, negative markers, textual equivalents, keyboard operation,
  persistence after refresh/restart, and no external network requests.
- **Catalog acceptance test**: all 100 shipped positions reconstruct and recompute to their stored
  White/Black expected sets under the pinned rules version.

### Coverage and Validation

- Follow repository guidance of greater than 80% automated code coverage.
- Critical domain rules, score/streak derivation, and transactional submission paths require full
  branch coverage through focused tests.
- Use `make test`, `make test-cov`, and `make check` as canonical validation entrypoints.
- Execute the PRD's P0 UAT scenarios before blueprint completion is claimed at product level.

## Dependencies

### External Dependencies

| Dependency | Lifecycle | Purpose | Risk and control |
|---|---|---|---|
| Flask | Runtime, locked | Local HTTP, templates, static files, JSON | Pin via lockfile; test app factory/routes |
| python-chess | Runtime, locked | FEN/UCI/attack maps | Pin version; golden rule fixtures and catalog version |
| Lichess puzzle snapshot | Build input only | Source positions/provenance | Record URL/date/checksum; no runtime dependency |
| zstandard support | Curation only | Stream `.zst` source | Keep outside runtime path where packaging permits |
| pytest/coverage/Ruff/pre-commit | Development | Verification and quality | Locked by `uv` |
| Playwright Python tooling | Development | Browser acceptance | Browser install is setup-only; runtime remains offline |

### Internal Dependencies

- Approved PRD and its classification semantics.
- Repository standards for Python 3.13+, `uv`, Make, typing, documentation, Ruff, and pytest.
- A generated catalog before the application can serve training positions.
- Locally writable instance directory for progress.

### Dependency Governance

- Commit `pyproject.toml` and `uv.lock`.
- Keep runtime dependencies minimal and explicitly separate curation/development extras.
- Record licenses and provenance for Lichess content and every dependency.
- No JavaScript package manager is required for the selected frontend.

## Implementation Plan

### Phase 1: Foundation and Rules

**Goals**: Establish reproducible tooling and the correctness-critical domain.

**Components**:

- Python package, `pyproject.toml`, `uv.lock`, Makefile, Ruff/pre-commit/pytest configuration.
- Domain models and `python-chess` adapter.
- Unit fixtures for attack/defense, pins, both colors, kings, and score algebra.

**Dependencies**: Approved PRD and architecture decisions.

**Deliverables**:

- Canonical setup/test/check/run commands.
- Passing correctness suite for the V1 classification contract.

### Phase 2: Dataset Curation and Catalog

**Goals**: Produce the complete immutable training set.

**Components**:

- Streaming Lichess parser and deterministic selection pipeline.
- Catalog schema, checksum, provenance, and validation command.
- Exactly 100 committed puzzle records with White/Black expected sets.

**Dependencies**: Phase 1 rule engine and an operator-supplied Lichess snapshot.

**Deliverables**:

- Versioned catalog and validation report/tests.
- Reproducible documented curation command.

### Phase 3: Durable Training Backend

**Goals**: Implement answer-safe puzzle delivery and atomic progress.

**Components**:

- Flask application factory and loopback configuration.
- Puzzle Catalog and Training Service.
- SQLite schema/repository, migrations, idempotency, statistics, and history.
- Versioned puzzle, attempt, stats, history, and health routes.

**Dependencies**: Phase 2 catalog.

**Deliverables**:

- Integration-tested backend that never leaks answers before submission.
- Transactional attempt behavior and recoverable error paths.

### Phase 4: Interactive Board and Feedback

**Goals**: Deliver the complete browser training workflow.

**Components**:

- Jinja shell and local CSS/JavaScript modules.
- Accessible custom board with both orientations.
- Four training-side options and two category controls.
- Positive tick, miss-color, and negative-marker result overlays plus text.
- Score strip, next-puzzle flow, statistics, and history.

**Dependencies**: Phase 3 routes and contracts.

**Deliverables**:

- Pointer- and keyboard-operable end-to-end application.
- Browser coverage of all P0 visual and workflow behavior.

### Phase 5: Hardening and Handoff

**Goals**: Prove local/offline operation and document ownership.

**Components**:

- Full automated and P0 UAT validation.
- Offline network assertion, restart persistence, and recovery exercises.
- README covering setup, run, tests, progress location/backup/reset, curation, and limitations.
- License/provenance inventory.

**Dependencies**: Phases 1-4.

**Deliverables**:

- Review-ready MVP and operating documentation.
- Evidence that all runtime assets and data remain local.

### Milestones

- **M1**: Classification contract proven.
- **M2**: Exactly 100 validated positions bundled.
- **M3**: Durable backend submission and statistics complete.
- **M4**: Interactive visual training workflow complete.
- **M5**: Offline, persistence, accessibility, and documentation gates pass.

No phase carries a calendar or duration commitment; ordering is dependency-based.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Misinterpreted attack/defense semantics | Medium | High | Golden fixtures for pinned pieces, pawns, kings, blockers, and both colors |
| Incorrect Lichess reconstruction | Medium | High | Always apply first UCI move and independently validate stored presented FEN |
| Answer leakage before submission | Medium | High | Backend-private answers; API contract and integration tests |
| Double or phantom attempts | Medium | High | Unique attempt ID, one SQLite transaction, commit-before-response |
| Progress corruption or incompatible schema | Low | High | Versioned migrations, transactional changes, explicit recovery, no silent reset |
| Board markers become ambiguous | Medium | Medium | Dedicated marker layers, legend, text equivalents, pointer/keyboard UAT |
| Miss color is inaccessible | Medium | Medium | Pair color with outline/pattern and text; contrast validation |
| Unicode chess glyph rendering varies | Medium | Low | Test supported browsers; keep renderer replaceable with locally bundled SVG later |
| Catalog cannot yield 100 useful positions | Low | Medium | Stream full source, deterministic filters, explicit failure without replacing output |
| External assets accidentally enter runtime | Low | High | CSP/network browser tests and local-only asset inventory |
| Greenfield tooling expands scope | Medium | Medium | Minimal dependency set, no Node/ORM/framework extras, phased gates |

## Open Questions

No blocking architecture questions remain. The exact accessible miss color and visual palette are a
design-token choice during implementation; the invariant is a dedicated miss treatment paired with
non-color meaning. If Unicode piece rendering fails supported-browser validation, locally bundled
SVG pieces may replace only the rendering adapter without changing board semantics.

## Success Metrics

### Technical Metrics

- Catalog validation passes for exactly 100 unique middlegame positions.
- Recomputed White/Black classifications match every stored catalog answer.
- No public puzzle response contains expected classification data.
- Attempt commit, score, and streak update succeed or roll back as one transaction.
- Duplicate attempt IDs create no additional history row.
- Browser network audit shows no non-loopback runtime requests.
- Progress survives browser refresh and application restart.
- Automated coverage exceeds the repository's 80% guideline, with complete critical-rule and
  transactional-path branch coverage.
- All P0 UAT scenarios pass; no timing or latency threshold is attached.

### Business Metrics

- The user can train under Side to move, White, Black, and Both scopes.
- Correct, missed, and incorrect pieces are understandable directly on the board and in text.
- Exact hanging-set score, accuracy, streaks, passive completion statistics, and history remain
  trustworthy across sessions.

## Related Documentation

- **PRD**: Upstream design input; not bundled in this repository.
- **Architecture Overview**: This technical blueprint is the repository architecture authority.
- **ADRs**: None yet. Decisions 1-6 are candidates if the project requires independent ADR records.
- **Mockups**: None; implementation-native layout is authorized by the PRD.
- **External References**:
  [Lichess Open Database](https://database.lichess.org/),
  [Flask Documentation](https://flask.palletsprojects.com/en/stable/),
  [Python sqlite3 Documentation](https://docs.python.org/3/library/sqlite3.html), and
  [python-chess Core Documentation](https://python-chess.readthedocs.io/en/latest/core.html).

## Appendix

### Glossary

- **Effective colors**: The actual White/Black set produced from a submitted scope.
- **Presentation identifier**: A backend-issued reference tying a browser exercise to one puzzle
  without containing expected answers.
- **Rule version**: Identifier for the exact classification semantics used to build and score a
  catalog/attempt.
- **Miss treatment**: Dedicated board color plus non-color styling and text for an expected piece
  the user did not select.

### Assumptions

- The application runs in one modern desktop browser on the same machine as the Python process.
- Side-to-move board orientation is independent of the selected classification scope.
- Completion duration remains passive history data and is never a scoring or performance target.
- The user supplies or explicitly authorizes acquisition of the large Lichess source snapshot when
  curation is implemented.

---

**Next Steps**:

1. Run the pending connected-browser acceptance checklist in `docs/acceptance.md`.
2. Refresh the stored official Lichess snapshot and regenerate the catalog when new puzzle data is
   intentionally adopted.
3. Create ADRs for decisions requiring long-lived independent governance.
