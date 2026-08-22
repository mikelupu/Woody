### EPIC-03-TRAINING-BACKEND: Durable Training Backend

**Epic Details:**
Implement the server-authoritative local backend: a validated runtime catalog, transactional SQLite
progress, submission verification, stable JSON routes, loopback security, and recoverable failure
semantics. Expected answers never leave the backend before a successful submission commit.

---

- [ ] **BCK-001: Implement the Runtime Puzzle Catalog and Selection Service**

**Issue Type:** Task

**Summary:** Implement the runtime puzzle catalog and selection service

**Effort Estimate:** Medium (for reference only)

**Labels:** backend, catalog, puzzles, validation

**Parent Epic:** EPIC-03-TRAINING-BACKEND (Durable Training Backend)

**Description:**
Load the shipped immutable catalog during application creation and expose a narrow runtime service
for answer-free puzzle presentation and private expected-answer lookup. Invalid catalogs must stop
training safely rather than allowing partial or stale content.

**Acceptance Criteria:**

- [ ] Startup validates schema/rules versions, catalog checksum, count, uniqueness, FENs, themes,
      answer invariants, and recomputed representative or complete classifications as configured by
      the blueprint's acceptance contract.
- [ ] Catalog validation failure prevents puzzle service readiness and provides an actionable local
      diagnostic without leaking the full catalog.
- [ ] Public puzzle views contain puzzle ID/public metadata, presented FEN, side to move, and opaque
      presentation ID but no expected undefended or hanging sets.
- [ ] Private lookup resolves expected sets for `side_to_move`, `white`, `black`, and `both`; Both is
      the normalized union of independently computed color results.
- [ ] Next-puzzle selection avoids the immediately previous puzzle when alternatives exist.
- [ ] Presentation IDs resolve only to valid catalog puzzles and invalid/stale IDs return stable
      application errors.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- Internal service supports the later `GET /api/v1/puzzles/next` route.

**Frontend Components (if any):**

- None.

**Dependencies:**

- Blocks: BCK-003 and BCK-004
- Is Blocked By: CAT-001 and CAT-003
- Related To: BCK-002 progress repository

**Testing Requirements:**

- Unit Tests: Valid/invalid catalog loading, answer-free projection, four scopes, Both union,
  selection behavior, and invalid presentation IDs.
- Integration Tests: Load the committed V1 catalog and prove public views omit answer fields.
- E2E Tests: None.
- Manual Testing: Inspect one public projection against its backend-only catalog record.

**Related Sections from Blueprint:**

- Component 3: Puzzle Catalog
- Load and classify interaction
- Data Models: PuzzleCatalog and Puzzle
- Decision 4: Immutable Catalog with Precomputed Answers

**Implementation Notes:**

- Never serialize private answer fields through public puzzle DTOs.
- Keep selection policy replaceable without introducing user accounts or persistent sessions.
- Catalog content remains read-only for the lifetime of the process.

**Definition of Done:**

- [ ] Runtime catalog and selection service are implemented and reviewed.
- [ ] Unit and catalog integration tests pass.
- [ ] Public/private projection boundaries are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **BCK-002: Implement SQLite Attempts, Migrations, and Derived Statistics**

**Issue Type:** Task

**Summary:** Implement SQLite attempts, migrations, and derived statistics

**Effort Estimate:** High (for reference only)

**Labels:** backend, sqlite, database, persistence, statistics

**Parent Epic:** EPIC-03-TRAINING-BACKEND (Durable Training Backend)

**Description:**
Create the versioned SQLite progress repository that atomically records append-only attempts and
derives all history and statistics. The repository must protect prior progress from duplicate
submissions, failed writes, corrupt state, and unsupported migrations.

**Acceptance Criteria:**

- [ ] A versioned schema stores the attempt identity, puzzle/presented FEN, submitted scope and
      effective colors, submitted/expected category sets, result, point, passive completion duration,
      commit timestamp, schema version, and rules version.
- [ ] Attempt ID has a uniqueness constraint; repeating an identical ID returns the original row and
      never adds another score/history event.
- [ ] Insert and any schema migration use explicit transactions with rollback on every failure path.
- [ ] History is append-only and ordered deterministically by commit sequence/time.
- [ ] Queries derive total attempts, score, exact-set accuracy, current streak, best streak, average
      completion duration, and most recent duration from committed attempts.
- [ ] Missing storage can initialize explicitly, while corrupt or unsupported existing schemas fail
      without deletion, replacement, or fabricated zero progress.
- [ ] The database defaults to Flask's local instance directory and is excluded from version control.

**Technical Details:**

**Database Changes (if any):**

- Table: schema metadata and append-only attempts
- Columns: all fields named in the Attempt blueprint model, using canonical JSON/text encoding for
  square sets
- Migrations: initial version plus transactional migration runner contract
- Indexes: unique attempt ID and history commit ordering

**API Endpoints (if any):**

- Internal repository supports later attempt, statistics, and history routes.

**Frontend Components (if any):**

- None.

**Dependencies:**

- Blocks: BCK-003 and BCK-004
- Is Blocked By: FND-001 and domain Attempt contracts from Epic 1
- Related To: BCK-001 runtime catalog

**Testing Requirements:**

- Unit Tests: Aggregate and streak derivations over empty, correct, incorrect, and mixed histories.
- Integration Tests: Initialization, migration, atomic insert/rollback, duplicate ID, ordering,
  restart persistence, corruption, and unsupported-version fixtures.
- E2E Tests: None.
- Manual Testing: Copy/restore a stopped test database and verify history remains readable.

**Related Sections from Blueprint:**

- Component 5: Progress Repository
- Data Models: Attempt
- Decision 5: SQLite as the Progress Authority
- Reliability & Operations: Data Recovery

**Implementation Notes:**

- Use parameterized SQL and Python's standard `sqlite3`; do not add an ORM.
- Store no independently mutable aggregate counters.
- Passive completion duration is informational and has no scoring or performance-target effect.

**Definition of Done:**

- [ ] Schema, migration runner, repository, and aggregate queries are implemented and reviewed.
- [ ] Transaction, idempotency, restart, and recovery tests pass.
- [ ] Schema and progress-file behavior are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **BCK-003: Implement the Training Submission and Feedback Service**

**Issue Type:** Task

**Summary:** Implement the training submission and feedback service

**Effort Estimate:** High (for reference only)

**Labels:** backend, service, scoring, feedback, transactions

**Parent Epic:** EPIC-03-TRAINING-BACKEND (Durable Training Backend)

**Description:**
Implement the application service that validates a provisional browser answer, resolves its scope,
compares it with private catalog answers, and commits one authoritative attempt. Feedback and
statistics are returned only after the repository confirms durable success.

**Acceptance Criteria:**

- [ ] The command validates attempt/presentation IDs, closed scope values, algebraic squares, set
      sizes, eligible colors/pieces, hanging-within-undefended input, and nonnegative bounded passive
      completion duration.
- [ ] `side_to_move` resolves from the presented FEN; White, Black, and Both preserve board
      orientation and resolve to their documented effective colors.
- [ ] Comparison returns correct, missed, and incorrect-extra sets independently for undefended and
      hanging categories.
- [ ] Exact expected/submitted hanging-set equality awards one point; every missing or extra hanging
      square awards zero and resets the current streak through the attempt ledger.
- [ ] The service commits the full audit attempt before returning feedback or updated statistics.
- [ ] Persistence failure returns a retryable error and produces no attempt, score, streak, or
      history change.
- [ ] Repeating a committed attempt ID returns the original result and statistics without duplicate
      work or a second attempt.

**Technical Details:**

**Database Changes (if any):**

- Uses the BCK-002 repository; no additional tables.

**API Endpoints (if any):**

- Internal command supports later `POST /api/v1/attempts`.

**Frontend Components (if any):**

- None; result DTOs expose marker-ready square sets and accessible piece/square descriptions.

**Dependencies:**

- Blocks: BCK-004 and EPIC-04-INTERACTIVE-BOARD
- Is Blocked By: BCK-001 and BCK-002
- Related To: FND-003 scoring and feedback algebra

**Testing Requirements:**

- Unit Tests: Validation matrix, four scopes, exact/extra/missed/empty submissions, feedback sets,
  and stable application errors.
- Integration Tests: Commit-before-result, rollback on repository failure, duplicate replay, and
  derived-statistic response.
- E2E Tests: None.
- Manual Testing: Review representative feedback DTOs for correct, missed, and incorrect pieces.

**Related Sections from Blueprint:**

- Component 4: Training Service
- Submit and review interaction
- Relationships and Invariants
- API Design: `POST /api/v1/attempts`

**Implementation Notes:**

- Inject catalog, repository, identifier generator, and clock interfaces.
- Never accept browser-computed correctness, point, streak, or expected sets.
- Keep visual color/tick decisions in the browser; return semantic outcome sets.

**Definition of Done:**

- [ ] Training submission service is implemented and reviewed.
- [ ] Validation, scoring, transaction, and idempotency tests pass.
- [ ] Command/result/error contracts are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **BCK-004: Implement the Flask API, Local Security, and Backend Integration Tests**

**Issue Type:** Task

**Summary:** Implement the Flask API, local security, and backend integration tests

**Effort Estimate:** High (for reference only)

**Labels:** backend, flask, api, security, integration-testing

**Parent Epic:** EPIC-03-TRAINING-BACKEND (Durable Training Backend)

**Description:**
Create the Flask application factory, local runtime configuration, server-rendered shell boundary,
and versioned JSON routes over the completed services. Prove answer secrecy, loopback defaults,
same-origin mutations, stable errors, and end-to-end backend transaction behavior.

**Acceptance Criteria:**

- [ ] Application creation injects catalog, training service, progress repository, identifiers, and
      clock without module-level mutable service singletons.
- [ ] `GET /api/v1/puzzles/next`, `POST /api/v1/attempts`, `GET /api/v1/stats`,
      `GET /api/v1/attempts`, and `GET /api/v1/health` expose the blueprint-defined behavior and
      stable JSON error envelope.
- [ ] Public puzzle and error responses contain no expected-answer fields or stack traces.
- [ ] Attempt mutation requires JSON and an allowed same-origin Origin; CORS is disabled.
- [ ] The normal run target binds to `127.0.0.1`, serves only locally bundled assets, and keeps
      debug/interactive debugger disabled; development reload behavior is isolated to `make dev`.
- [ ] Health output reports catalog/database readiness without personal attempt data.
- [ ] Integration tests prove valid flow, invalid inputs, stale presentation, duplicate attempt,
      repository rollback, restart persistence, answer secrecy, and local security headers/policy.

**Technical Details:**

**Database Changes (if any):**

- Uses BCK-002 schema and migration initialization.

**API Endpoints (if any):**

- Method: GET; Path: `/api/v1/puzzles/next`; response is answer-free puzzle presentation.
- Method: POST; Path: `/api/v1/attempts`; request is scoped selections; response is committed review
  and statistics.
- Method: GET; Paths: `/api/v1/stats`, `/api/v1/attempts`, `/api/v1/health`.
- Status Codes: 200 success/replay, 400 malformed input, 403 origin/policy rejection, 404 unknown
  presentation, 409 incompatible/conflicting state, 500 recoverable local service failure.

**Frontend Components (if any):**

- Jinja shell route and static-file mounting only; interactive UI belongs to Epic 4.

**Dependencies:**

- Blocks: All EPIC-04-INTERACTIVE-BOARD tickets
- Is Blocked By: BCK-001, BCK-002, and BCK-003
- Related To: FND-001 Make run/dev targets

**Testing Requirements:**

- Unit Tests: Route request/response validation and error mapping.
- Integration Tests: Full Flask test-client flow and all acceptance criteria.
- E2E Tests: Deferred to Epic 4/5 browser coverage.
- Manual Testing: Start through `make run` and verify loopback binding and debug-off behavior.

**Related Sections from Blueprint:**

- Component 6: Flask Web Layer
- API Design
- Decision 6: Loopback-Only, Same-Origin Runtime
- Security Considerations
- Reliability & Operations

**Implementation Notes:**

- Keep route functions thin and delegate semantics to application services.
- Do not enable LAN binding as a casual configuration option.
- Jinja auto-escaping stays enabled and no remote scripts, fonts, styles, or telemetry are used.

**Definition of Done:**

- [ ] Flask application, routes, run/dev behavior, and policies are implemented and reviewed.
- [ ] Backend integration and security tests pass.
- [ ] API behavior and local startup are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.
