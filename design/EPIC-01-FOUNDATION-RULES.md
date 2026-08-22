### EPIC-01-FOUNDATION-RULES: Foundation & Chess Rules

**Epic Details:**
Establish the reproducible Python foundation and the correctness-critical, framework-independent
chess domain. Deliver position reconstruction, scope resolution, pin-agnostic classification,
exact-set scoring, feedback-set algebra, and golden tests that downstream epics can trust.

---

- [ ] **FND-001: Bootstrap Python Project and Developer Tooling**

**Issue Type:** Task

**Summary:** Bootstrap Python project and developer tooling

**Effort Estimate:** Low (for reference only)

**Labels:** foundation, python, tooling, testing

**Parent Epic:** EPIC-01-FOUNDATION-RULES (Foundation & Chess Rules)

**Description:**
Create the minimal Python project and quality-tool foundation required by the repository. The result
must give every later ticket reproducible dependencies, a typed package boundary, and canonical Make
entrypoints for installation, linting, formatting, tests, and coverage.

**Acceptance Criteria:**

- [ ] `pyproject.toml` requires Python 3.13+ and separates runtime, curation, browser-test, and
      development dependencies without adding an ORM or frontend toolchain.
- [ ] `uv.lock` is generated from the declared dependencies and supports a clean environment setup.
- [ ] The application package and test package are importable through the configured project layout.
- [ ] Make targets provide `setup`, `install`, `check`, `fix`, `lint`, `format`, `test`, and
      `test-cov` through `uv` and the configured tools.
- [ ] Ruff, pre-commit, pytest, and coverage enforce the repository's 100-character line length,
      typing/documentation expectations, and greater-than-80% coverage guideline.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- None.

**Frontend Components (if any):**

- None.

**Dependencies:**

- Blocks: FND-002, FND-003, and EPIC-02-PUZZLE-CATALOG
- Is Blocked By: None
- Related To: Repository coding standards and application-tooling rules

**Testing Requirements:**

- Unit Tests: Add a minimal package/test smoke test proving the configured import path.
- Integration Tests: Run the canonical Make validation entrypoints in a clean environment.
- E2E Tests: None.
- Manual Testing: Confirm documented setup completes without undeclared global Python packages.

**Related Sections from Blueprint:**

- Technical Context
- Technology Stack
- Architectural Principles
- Phase 1: Foundation and Rules

**Implementation Notes:**

- Use `uv` for dependency resolution and execution; Make remains the user-facing task runner.
- Keep runtime dependencies limited to those authorized by the blueprint.
- Extend `.gitignore` for local environments, coverage artifacts, generated caches, and progress
  data without modifying sensitive paths.

**Definition of Done:**

- [ ] Project/tooling files are implemented and reviewed.
- [ ] Smoke tests and canonical validation commands pass.
- [ ] Setup and validation entrypoints are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **FND-002: Implement Chess Reconstruction and Domain Contracts**

**Issue Type:** Task

**Summary:** Implement chess reconstruction and domain contracts

**Effort Estimate:** Medium (for reference only)

**Labels:** backend, domain, chess-rules, python

**Parent Epic:** EPIC-01-FOUNDATION-RULES (Foundation & Chess Rules)

**Description:**
Define stable domain value objects and reconstruct the position a learner must see from a Lichess
source FEN and first UCI move. This ticket creates the shared validation and normalization boundary
used by both catalog curation and runtime catalog verification.

**Acceptance Criteria:**

- [ ] Typed domain contracts represent colors, classification scopes, normalized board squares,
      presented positions, and per-color classification results without leaking `python-chess`
      objects.
- [ ] Reconstruction parses the source FEN, validates the first UCI move, applies it exactly once,
      and returns a canonical presented FEN and side to move.
- [ ] Malformed FENs, malformed/illegal first moves, non-standard positions, missing kings, and
      otherwise invalid results produce stable domain errors.
- [ ] Square sets are normalized, duplicate-free, deterministically ordered at serialization
      boundaries, and restricted to valid algebraic squares.
- [ ] Public modules, classes, and functions follow repository typing and documentation standards.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- None; these are internal domain contracts.

**Frontend Components (if any):**

- None.

**Dependencies:**

- Blocks: FND-003 and EPIC-02-PUZZLE-CATALOG tickets
- Is Blocked By: FND-001
- Related To: Lichess puzzle-format contract

**Testing Requirements:**

- Unit Tests: Valid White/Black examples, invalid FENs, malformed/illegal moves, canonical FEN, and
  square normalization.
- Integration Tests: Cross-check sampled reconstruction against documented Lichess examples.
- E2E Tests: None.
- Manual Testing: None beyond fixture review.

**Related Sections from Blueprint:**

- Data Flow and Trust Boundaries
- Component 1: Curation Pipeline
- Component 2: Chess Classification Domain
- Data Models: Puzzle
- Decision 3: `python-chess` for Pin-Agnostic Attack Maps

**Implementation Notes:**

- Keep library board objects inside a narrow adapter to avoid Z200-LEAKY-ABSTRACTION.
- The first Lichess move produces the presented position; the second move is not part of this
  training workflow.
- Do not introduce catalog I/O, Flask, or persistence responsibilities.

**Definition of Done:**

- [ ] Domain contracts and reconstruction are implemented and reviewed.
- [ ] Unit and integration tests pass.
- [ ] Public API documentation is complete.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **FND-003: Implement Piece-Safety Classification, Scoring, and Golden Tests**

**Issue Type:** Task

**Summary:** Implement piece-safety classification, scoring, and golden tests

**Effort Estimate:** High (for reference only)

**Labels:** backend, domain, chess-rules, scoring, testing

**Parent Epic:** EPIC-01-FOUNDATION-RULES (Foundation & Chess Rules)

**Description:**
Implement the normative V1 rules for undefended and hanging pieces, classification-scope
resolution, exact hanging-set scoring, and review feedback. Golden fixtures must make the subtle
pin-agnostic behavior explicit so curation and runtime verification remain consistent.

**Acceptance Criteria:**

- [ ] Each eligible non-king piece is undefended exactly when it has no same-color geometric
      attacker/defender under the documented occupied-board semantics.
- [ ] Each eligible piece is hanging exactly when it is undefended and attacked by at least one
      opposite-color piece; every hanging result is included in undefended.
- [ ] Pinned attackers and defenders count geometrically, friendly king protection counts, and the
      kings themselves are never classified.
- [ ] `side_to_move`, `white`, `black`, and `both` resolve to correct eligible color sets without
      changing board orientation.
- [ ] Exact hanging-set equality awards one point; missing or extra hanging selections award zero.
- [ ] Result comparison returns correct, missed, and incorrect-extra square sets independently for
      undefended and hanging categories.
- [ ] Golden fixtures cover pawns, sliding blockers, knights, king defenders, pinned attackers,
      pinned defenders, both sides to move, Both scope, empty submissions, and extra selections.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- None; the functions are consumed by later application services.

**Frontend Components (if any):**

- None; feedback outcomes are domain sets rather than visual markers.

**Dependencies:**

- Blocks: All EPIC-02-PUZZLE-CATALOG work and runtime answer verification
- Is Blocked By: FND-001 and FND-002
- Related To: PRD classification definitions and feedback requirements

**Testing Requirements:**

- Unit Tests: Exhaustive focused tests for every acceptance criterion and invariant.
- Integration Tests: Verify `python-chess` pinned-piece semantics through the adapter.
- E2E Tests: None.
- Manual Testing: Product-owner review of representative golden positions and expected square sets.

**Related Sections from Blueprint:**

- Component 2: Chess Classification Domain
- Component 4: Training Service
- Relationships and Invariants
- Decision 3: `python-chess` for Pin-Agnostic Attack Maps
- Testing Strategy: Domain unit tests

**Implementation Notes:**

- Prefer pure functions and immutable result values.
- Treat attack/defense vocabulary from the approved PRD as normative.
- Do not add material values, exchange heuristics, engine evaluation, pin-aware logic, or timing.

**Definition of Done:**

- [ ] Classification, scope, scoring, and feedback logic are implemented and reviewed.
- [ ] Critical rule and scoring branches have complete focused coverage.
- [ ] Golden fixtures are readable and document their chess intent.
- [ ] Product-owner fixture review is recorded.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.
