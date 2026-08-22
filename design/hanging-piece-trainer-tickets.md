---
generated: 2026-08-09
source_blueprint: design/blueprint.md
blueprint_id: hanging-piece-trainer
total_tickets: 17
epics_count: 5
status: ready
---

# Implementation Tickets: Hanging Piece Trainer

> **Implemented product simplification (2026-08-10):** The delivered training workflow collects
> only hanging-piece selections. Undefended classification remains internal. This supersedes the
> dual-category UI/request acceptance language retained in the original ticket record.

**Source Blueprint:**
[`design/blueprint.md`](./blueprint.md)

## Summary

This finalized ticket bundle contains the approved implementation tickets for Hanging Piece Trainer.
All five epics and their detailed tickets have completed review.

**Final Stats:**

- Detailed Tickets: 17
- Epic Definitions: 5
- Ticket Effort Breakdown: 8 High, 8 Medium, 1 Low
- Epic Effort Breakdown: 3 High, 2 Medium

**Approved Epic Overview:**

- EPIC-01-FOUNDATION-RULES: Foundation & Chess Rules (3 tickets, Medium)
- EPIC-02-PUZZLE-CATALOG: Puzzle Curation & Catalog (3 tickets, High)
- EPIC-03-TRAINING-BACKEND: Durable Training Backend (4 tickets, High)
- EPIC-04-INTERACTIVE-BOARD: Interactive Board & Feedback (4 tickets, High)
- EPIC-05-HARDENING-HANDOFF: Hardening & Handoff (3 tickets, Medium)

**Planned Implementation Order:**

1. Foundation & Chess Rules
2. Puzzle Curation & Catalog
3. Durable Training Backend
4. Interactive Board & Feedback
5. Hardening & Handoff

**Dependency Graph:**

```text
Epic 1: Foundation & Chess Rules
  └─> Epic 2: Puzzle Curation & Catalog
       └─> Epic 3: Durable Training Backend
            └─> Epic 4: Interactive Board & Feedback
                 └─> Epic 5: Hardening & Handoff
```

---

## Epic Tickets

- [ ] **EPIC-01-FOUNDATION-RULES: Foundation & Chess Rules**

**Issue Type:** Epic

**Summary:** Foundation & Chess Rules

**Effort Estimate:** Medium (for reference only)

**Labels:** foundation, python, chess-rules, testing, tooling

**Description:**
Establish the reproducible Python development foundation and the correctness-critical chess domain.
This epic owns position reconstruction, pin-agnostic piece-safety classification, scope resolution,
scoring, feedback-set algebra, and their golden fixtures so downstream dataset and application work
depend on one proven rules authority.

**Scope:**

- [ ] Python 3.13+, `uv`, Make, Ruff, pre-commit, pytest, and coverage setup
- [ ] Framework-independent chess domain contracts and `python-chess` adapter
- [ ] Lichess FEN plus first-move reconstruction and validation
- [ ] White, Black, Both, and Side-to-move scope resolution
- [ ] Undefended/hanging classification, exact-set scoring, and feedback-set calculation

**Key Deliverables:**

- Reproducible dependency and quality-tool configuration
- Pure, typed chess-domain package with stable value objects and errors
- Golden fixture suite covering pins, pawns, kings, blockers, both colors, scoring, and feedback

**Dependencies:**

- Depends on: Approved Hanging Piece Trainer PRD and technical blueprint
- Blocks: EPIC-02-PUZZLE-CATALOG

**Acceptance Criteria:**

- [ ] `make setup`, `make test`, `make test-cov`, and `make check` are canonical and functional.
- [ ] Presented positions are reconstructed by applying the first Lichess UCI move and invalid input
      is rejected deterministically.
- [ ] Pinned pieces count geometrically as attackers and defenders, kings are not classified, and
      every hanging set remains a subset of its undefended set.
- [ ] Side to move, White, Black, and Both scopes resolve to correct eligible color sets.
- [ ] Exact hanging-set scoring and correct/missed/incorrect feedback sets are covered by focused
      automated tests.

**Related Blueprint Sections:**

- Technology Stack
- Architectural Principles
- Component 2: Chess Classification Domain
- Decision 3: `python-chess` for Pin-Agnostic Attack Maps
- Testing Strategy
- Phase 1: Foundation and Rules

**Notes:**
Keep Flask, SQLite, JSON catalog paths, and browser types outside the chess domain. Apply
Y100-SINGLE-RESPONSIBILITY and Y103-DEPENDENCY-INJECTION; avoid Z102-GOD-OBJECTS and
Z200-LEAKY-ABSTRACTION.

---

- [ ] **EPIC-02-PUZZLE-CATALOG: Puzzle Curation & Catalog**

**Issue Type:** Epic

**Summary:** Puzzle Curation & Catalog

**Effort Estimate:** High (for reference only)

**Labels:** data, curation, lichess, catalog, validation

**Description:**
Create the deterministic build-time pipeline and immutable runtime catalog for the fixed training
set. This epic converts explicitly supplied Lichess puzzle data into exactly 100 validated
middlegame positions with provenance and precomputed White/Black answers, while keeping the large
source dataset and all network activity outside application runtime.

**Scope:**

- [ ] Versioned puzzle-catalog schema, provenance, rules version, and checksums
- [ ] Streaming compressed/decompressed Lichess CSV ingestion
- [ ] First-move reconstruction, theme/legality checks, and classification validation
- [ ] Deterministic selection of exactly 100 unique eligible positions
- [ ] Shipped-catalog recomputation and acceptance validation

**Key Deliverables:**

- Stable catalog contract and validator
- Reproducible curation command with atomic safe-failure behavior
- Committed catalog containing exactly 100 validated puzzles and their private answers

**Dependencies:**

- Depends on: FND-002, FND-003, and an operator-supplied or explicitly authorized Lichess snapshot
- Blocks: EPIC-03-TRAINING-BACKEND

**Acceptance Criteria:**

- [ ] Catalog metadata records schema/rules versions, source provenance/checksum, deterministic seed,
      and catalog checksum.
- [ ] Curation applies the first UCI move and accepts only valid standard-chess records containing
      the exact `middlegame` theme token.
- [ ] Every selected position has at least one hanging piece for its side to move.
- [ ] Output contains exactly 100 unique puzzle IDs with normalized White and Black expected sets.
- [ ] Identical source, rules, and seed inputs produce byte-stable canonical content.
- [ ] Invalid or insufficient input fails without replacing an existing valid catalog.
- [ ] Acceptance validation reconstructs every position and matches all stored classifications.

**Related Blueprint Sections:**

- Component 1: Curation Pipeline
- Component 3: Puzzle Catalog
- Data Models: PuzzleCatalog and Puzzle
- Decision 4: Immutable Catalog with Precomputed Answers
- Testing Strategy: Curation and catalog acceptance tests
- Phase 2: Dataset Curation and Catalog

**Notes:**
The curation tool accepts a local source path. Acquiring the large Lichess snapshot is an explicit
operator action and is not silently performed by setup, tests, or runtime.

---

- [ ] **EPIC-03-TRAINING-BACKEND: Durable Training Backend**

**Issue Type:** Epic

**Summary:** Durable Training Backend

**Effort Estimate:** High (for reference only)

**Labels:** backend, flask, sqlite, api, security, testing

**Description:**
Build the server-authoritative local application core that safely serves answer-free puzzles,
verifies submissions, commits append-only attempts, and derives trustworthy progress. This epic
also establishes the loopback-only Flask API and the failure semantics required before the browser
can become a durable training client.

**Scope:**

- [ ] Runtime puzzle-catalog validation, lookup, and answer-safe public views
- [ ] SQLite schema, migrations, append-only attempts, idempotency, and derived statistics
- [ ] Training submission orchestration and feedback-set calculation
- [ ] Flask application factory, versioned JSON routes, loopback/same-origin controls, and errors
- [ ] Backend integration tests for commit, rollback, duplicate, recovery, and answer leakage

**Key Deliverables:**

- Runtime catalog and puzzle-presentation service
- Transactional local progress repository and aggregate queries
- Versioned puzzle, attempt, statistics, history, and health API
- Integration-tested local security and recoverable error behavior

**Dependencies:**

- Depends on: EPIC-02-PUZZLE-CATALOG and its validated V1 catalog
- Blocks: EPIC-04-INTERACTIVE-BOARD

**Acceptance Criteria:**

- [ ] Public puzzle responses contain no expected classifications.
- [ ] All four training scopes resolve and verify on the server.
- [ ] Attempts commit atomically and duplicate attempt IDs create no extra history rows.
- [ ] Failed writes leave attempts, score, streaks, and history unchanged.
- [ ] Aggregate statistics derive from committed attempts rather than duplicated mutable counters.
- [ ] Corrupt or unsupported progress schemas fail clearly without silent reset.
- [ ] Normal runtime binds to loopback, disables CORS, validates same-origin JSON writes, and keeps
      debug mode off.
- [ ] Backend tests cover success, validation, duplicate, rollback, recovery, and answer secrecy.

**Related Blueprint Sections:**

- Components 3-6
- Data Models: Attempt
- API Design
- Decisions 4-6
- Security Considerations
- Reliability & Operations
- Phase 3: Durable Training Backend

**Notes:**
SQLite is the sole progress authority. The browser must not advance score or streaks before a
submission transaction commits.

---

- [ ] **EPIC-04-INTERACTIVE-BOARD: Interactive Board & Feedback**

**Issue Type:** Epic

**Summary:** Interactive Board & Feedback

**Effort Estimate:** High (for reference only)

**Labels:** frontend, accessibility, chessboard, feedback, statistics

**Description:**
Deliver the complete browser training workflow on top of the durable backend. This epic owns the
accessible board, four classification scopes, category-state rules, board-level result markers,
text feedback, navigation, and committed progress views without adding a frontend framework or
remote runtime assets.

**Scope:**

- [ ] Jinja shell and locally bundled modular JavaScript/CSS
- [ ] Accessible custom 8×8 button-grid board with both orientations
- [ ] Side to move, White, Black, and Both scope controls
- [ ] Undefended/hanging selection state and eligibility rules
- [ ] Positive ticks, miss-color highlights, negative markers, and equivalent text
- [ ] Next-puzzle, score/statistics, history, loading, and recoverable error states

**Key Deliverables:**

- Pointer- and keyboard-operable training board
- Correct classification-selection behavior for every scope
- Accessible visual review experience with committed score/history updates
- Focused browser/component tests for the complete training workflow

**Dependencies:**

- Depends on: EPIC-03-TRAINING-BACKEND
- Blocks: EPIC-05-HARDENING-HANDOFF

**Acceptance Criteria:**

- [ ] Board orientation follows the position's side to move and every square has accessible labels.
- [ ] New puzzles default to Side to move; White, Black, and Both change eligibility without
      rotating the board.
- [ ] Hanging implies undefended, and removing undefended removes hanging.
- [ ] Correct pieces receive positive ticks, missed pieces receive the dedicated miss treatment,
      and incorrect extras receive distinct negative markers with equivalent text.
- [ ] Failed submissions preserve editable selections and never advance displayed progress.
- [ ] Navigation, statistics, and history reflect only backend-committed data.
- [ ] All runtime scripts, styles, glyphs, and assets are local.

**Related Blueprint Sections:**

- Component 7: Browser Training UI
- Load and classify / Submit and review interactions
- Decision 2: Custom Accessible Selection Board
- API Design
- User-facing portions of Testing Strategy
- Phase 4: Interactive Board and Feedback

**Notes:**
The dedicated miss color must also use outline/pattern and text so it is not a color-only signal.
Visual styling does not change the semantic correct/missed/incorrect sets returned by the backend.

---

- [ ] **EPIC-05-HARDENING-HANDOFF: Hardening & Handoff**

**Issue Type:** Epic

**Summary:** Hardening & Handoff

**Effort Estimate:** Medium (for reference only)

**Labels:** testing, accessibility, offline, documentation, release

**Description:**
Prove that the completed local application satisfies its cross-layer correctness, accessibility,
offline, durability, and operating requirements. This epic closes gaps that individual component
tests cannot prove and delivers the documentation, provenance, and acceptance evidence needed for
a trustworthy personal release.

**Scope:**

- [ ] Browser-level workflow, accessibility, offline, and restart validation
- [ ] Full-catalog, critical-rule, transaction, and recovery verification
- [ ] Setup, operation, progress backup/reset/recovery, curation, and troubleshooting documentation
- [ ] Dependency/data provenance and license inventory
- [ ] Final P0 UAT execution, evidence, and handoff summary

**Key Deliverables:**

- Repeatable browser acceptance suite and local-only network audit
- Complete user/developer operating guide and provenance inventory
- Final P0 acceptance record with no unresolved release blockers

**Dependencies:**

- Depends on: EPIC-01-FOUNDATION-RULES through EPIC-04-INTERACTIVE-BOARD
- Blocks: Initial release completion

**Acceptance Criteria:**

- [ ] Canonical validation commands and required coverage pass.
- [ ] Browser tests cover both orientations, all scopes, feedback markers/text, retry, navigation,
      statistics, history, refresh, and restart.
- [ ] Runtime network audit shows no non-loopback request.
- [ ] Progress backup, restore, corruption, unsupported schema, and explicit reset procedures work as
      documented without silent data loss.
- [ ] All 100 catalog entries pass reconstruction and answer recomputation.
- [ ] Setup, operation, recovery, curation, limitations, troubleshooting, and provenance are
      documented.
- [ ] Every P0 PRD scenario passes with evidence and no timing threshold is introduced.

**Related Blueprint Sections:**

- Testing Strategy
- Security Considerations
- Reliability & Operations
- Dependencies and Dependency Governance
- Success Metrics
- Phase 5: Hardening and Handoff

**Notes:**
This epic verifies already-authorized behavior; it must not expand the MVP with adaptive training,
mobile polish, accounts, cloud services, or performance targets.

---

## Implementation Tickets by Epic

Detailed task tickets are organized in separate epic files.

**Epic Ticket Files:**

- [EPIC-01-FOUNDATION-RULES](./EPIC-01-FOUNDATION-RULES.md) -
  Foundation & Chess Rules (3 tickets)
- [EPIC-02-PUZZLE-CATALOG](./EPIC-02-PUZZLE-CATALOG.md) -
  Puzzle Curation & Catalog (3 tickets)
- [EPIC-03-TRAINING-BACKEND](./EPIC-03-TRAINING-BACKEND.md) -
  Durable Training Backend (4 tickets)
- [EPIC-04-INTERACTIVE-BOARD](./EPIC-04-INTERACTIVE-BOARD.md) -
  Interactive Board & Feedback (4 tickets)
- [EPIC-05-HARDENING-HANDOFF](./EPIC-05-HARDENING-HANDOFF.md) -
  Hardening & Handoff (3 tickets)

**Note:** Epic definitions remain in this document. The linked files are the durable source for
detailed task descriptions, acceptance criteria, dependencies, and definitions of done.
