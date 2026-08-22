### EPIC-04-INTERACTIVE-BOARD: Interactive Board & Feedback

**Epic Details:**
Build the accessible browser experience for classifying pieces and reviewing committed results.
The frontend remains framework-free, treats the backend as progress authority, bundles every
runtime asset locally, and pairs all visual feedback with equivalent text.

---

- [ ] **UI-001: Build the Accessible Chessboard and Application Shell**

**Issue Type:** Task

**Summary:** Build the accessible chessboard and application shell

**Effort Estimate:** High (for reference only)

**Labels:** frontend, chessboard, accessibility, jinja, css

**Parent Epic:** EPIC-04-INTERACTIVE-BOARD (Interactive Board & Feedback)

**Description:**
Create the server-rendered application shell and custom semantic 8×8 chessboard. The board must
render a presented FEN correctly for either orientation and provide a stable, accessible base for
selection and result marker layers.

**Acceptance Criteria:**

- [ ] The Flask shell loads only locally bundled HTML, modular JavaScript, CSS, and chess glyphs;
      no CDN, remote font, analytics, or telemetry request is present.
- [ ] The board renders all pieces and coordinates from the presented FEN and places the side to
      move at the bottom for both White- and Black-to-move positions.
- [ ] All 64 squares use semantic keyboard-focusable controls with accessible labels containing
      square, piece/color when occupied, and current interaction state.
- [ ] Arrow-key or documented keyboard navigation, visible focus, pointer activation, and logical
      focus order work for both orientations.
- [ ] Marker layers can independently display provisional categories and later correct, missed,
      and incorrect outcomes without changing piece identity or square geometry.
- [ ] Loading, catalog-unavailable, and puzzle-fetch failure states are clear and do not show a
      partially interactive invalid board.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- Consumes `GET /api/v1/puzzles/next`.

**Frontend Components (if any):**

- Component Name: Application shell, board renderer, square button, coordinate labels, marker layer
- Props: Public puzzle presentation and view state
- State: Current puzzle/loading/error only; selection state belongs to UI-002
- Styling: Local CSS grid with orientation-aware ordering and focus/marker tokens

**Dependencies:**

- Blocks: UI-002 and UI-003
- Is Blocked By: BCK-004
- Related To: UI-004 navigation

**Testing Requirements:**

- Unit Tests: FEN-to-view-model conversion, square ordering, coordinate labels, and accessible names.
- Integration Tests: Shell/static asset loading and answer-free puzzle rendering.
- E2E Tests: White/Black orientation, keyboard focus/navigation, pointer activation, and fetch errors.
- Manual Testing: Inspect supported desktop browser glyph rendering and focus visibility.

**Related Sections from Blueprint:**

- Component 7: Browser Training UI
- Decision 2: Custom Accessible Selection Board
- Load and classify interaction
- Security Considerations: local runtime assets

**Implementation Notes:**

- Keep board coordinates and orientation in a pure view-model module.
- Unicode glyph rendering is the V1 adapter; do not introduce movement or drag-and-drop behavior.
- Do not expose backend-private answer fields in HTML or JavaScript.

**Definition of Done:**

- [ ] Shell and board are implemented and reviewed.
- [ ] Unit, integration, and focused browser tests pass.
- [ ] Keyboard and accessibility behavior are documented.
- [ ] No linter, formatting, or external-asset errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **UI-002: Implement Scope and Classification Selection State**

**Issue Type:** Task

**Summary:** Implement scope and classification selection state

**Effort Estimate:** Medium (for reference only)

**Labels:** frontend, state-management, chessboard, accessibility

**Parent Epic:** EPIC-04-INTERACTIVE-BOARD (Interactive Board & Feedback)

**Description:**
Implement the provisional browser state for choosing the training side and marking pieces as
undefended or hanging. State transitions must enforce the PRD's eligibility and category
invariants without revealing whether a provisional answer is correct.

**Acceptance Criteria:**

- [ ] Every newly loaded puzzle resets scope to Side to move and clears provisional selections.
- [ ] Scope controls offer Side to move, White, Black, and Both; changing scope never changes board
      orientation.
- [ ] Only non-king pieces whose colors are eligible under the active scope can be selected; invalid
      activation leaves state unchanged and announces why.
- [ ] Undefended and hanging modes are clearly labeled and keyboard operable; provisional styling
      communicates only the selected category, never correctness.
- [ ] Selecting hanging also selects undefended; removing undefended also removes hanging; removing
      hanging leaves undefended selected.
- [ ] Changing scope removes now-ineligible selections while preserving selections that remain
      eligible.
- [ ] Submission-ready state serializes canonical duplicate-free square sets and the explicit scope.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- Produces the selection portion of `POST /api/v1/attempts` requests.

**Frontend Components (if any):**

- Component Name: Training-side selector, category selector, board selection controller
- Props: Puzzle side to move and occupied-square eligibility map
- State: Active scope, active category, undefended set, hanging set, submission lock
- Styling: Distinct category markers with labels/icons and non-color semantics

**Dependencies:**

- Blocks: UI-003
- Is Blocked By: UI-001 and BCK-003 request contract
- Related To: UI-004 next-puzzle reset

**Testing Requirements:**

- Unit Tests: Every state transition, category invariant, scope resolution, eligibility, canonical
  serialization, and reset behavior.
- Integration Tests: Request payload compatibility with BCK-003 validation.
- E2E Tests: Four scopes, both orientations, keyboard/pointer selection, invalid pieces/kings, and
  absence of pre-submit correctness cues.
- Manual Testing: Confirm controls and provisional markers are understandable without instructions.

**Related Sections from Blueprint:**

- Component 7: Browser Training UI
- Load and classify interaction
- Relationships and Invariants
- Business Metrics: four training scopes

**Implementation Notes:**

- Use one explicit client state owner rather than state encoded only in DOM classes.
- Keep expected-answer and scoring logic out of the browser.
- Do not add timing-dependent transitions or timed scoring.

**Definition of Done:**

- [ ] Scope and selection behavior are implemented and reviewed.
- [ ] Unit, integration, and browser tests pass.
- [ ] State invariants and keyboard behavior are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **UI-003: Implement Submission and Visual Review Feedback**

**Issue Type:** Task

**Summary:** Implement submission and visual review feedback

**Effort Estimate:** High (for reference only)

**Labels:** frontend, feedback, accessibility, api, chessboard

**Parent Epic:** EPIC-04-INTERACTIVE-BOARD (Interactive Board & Feedback)

**Description:**
Connect provisional selections to the authoritative submission API and render its committed review
semantics directly on the board. Correct pieces, misses, and incorrect extras must have distinct
visual and textual treatments, and failure must preserve the answer for retry.

**Acceptance Criteria:**

- [ ] Check Answer sends one client-generated attempt ID, presentation ID, active scope, canonical
      category sets, and passive completion duration; duplicate activation cannot create a second
      attempt.
- [ ] The answer remains editable during recoverable request/persistence failure, and no local score,
      streak, history, or review marker is advanced before a committed response.
- [ ] A committed result locks the submitted answer and places a positive tick on each correct piece
      for its applicable category.
- [ ] Every missed piece receives the dedicated miss-color highlight plus a non-color outline/pattern
      and accessible text naming piece, color, square, category, and missed outcome.
- [ ] Every incorrect extra receives a distinct negative marker and equivalent accessible text.
- [ ] Overlapping undefended/hanging outcomes remain understandable when one square has multiple
      category results.
- [ ] The feedback panel states point earned and lists every correct, missed, and incorrect result;
      focus/announcement moves to the result without trapping keyboard navigation.

**Technical Details:**

**Database Changes (if any):**

- None; committed persistence is owned by BCK-002/BCK-003.

**API Endpoints (if any):**

- Method: POST
- Path: `/api/v1/attempts`
- Request Schema: Attempt/presentation IDs, scope, category square sets, passive completion duration
- Response Schema: Commit identity, point/result, semantic feedback sets/text data, and statistics
- Status Codes: Handle success/replay, validation, stale presentation, policy, conflict, and retryable
  local failure according to BCK-004

**Frontend Components (if any):**

- Component Name: Submission controller, board result-marker renderer, feedback panel
- Props: Provisional state and committed attempt response
- State: Submitting, editable error, committed review
- Styling: Positive tick, dedicated miss treatment, distinct negative marker, accessible legend

**Dependencies:**

- Blocks: UI-004 and EPIC-05-HARDENING-HANDOFF
- Is Blocked By: UI-001, UI-002, BCK-003, and BCK-004
- Related To: Backend idempotency and rollback tests

**Testing Requirements:**

- Unit Tests: Response-to-marker mapping, overlapping outcomes, submission lock, and recoverable error
  state.
- Integration Tests: API success, replay, validation, stale presentation, and persistence failure.
- E2E Tests: Positive ticks, miss color/non-color cue, negative markers, text equivalence, focus
  announcement, duplicate click, and retry without lost selections.
- Manual Testing: Product-owner review of representative correct, missed, incorrect, and overlapping
  result boards.

**Related Sections from Blueprint:**

- Submit and review interaction
- Component 7: Browser Training UI
- API Design: `POST /api/v1/attempts`
- Risks: board-marker ambiguity and miss-color accessibility

**Implementation Notes:**

- Render semantic backend outcomes; do not recompute correctness in JavaScript.
- Choose exact color tokens during implementation and verify contrast; color alone is insufficient.
- Keep passive completion duration separate from point/result rendering.

**Definition of Done:**

- [ ] Submission and review experience are implemented and reviewed.
- [ ] Unit, integration, browser, and accessibility-focused tests pass.
- [ ] Marker legend and retry behavior are documented.
- [ ] Product-owner visual review is recorded.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **UI-004: Implement Puzzle Navigation, Statistics, and History Views**

**Issue Type:** Task

**Summary:** Implement puzzle navigation, statistics, and history views

**Effort Estimate:** Medium (for reference only)

**Labels:** frontend, statistics, history, navigation, api

**Parent Epic:** EPIC-04-INTERACTIVE-BOARD (Interactive Board & Feedback)

**Description:**
Complete the browser workflow with next-puzzle navigation and read-only progress views. The UI must
display only committed backend statistics/history and preserve clear recovery behavior when reads
or navigation fail.

**Acceptance Criteria:**

- [ ] Next Puzzle is available after committed review, requests another puzzle while avoiding the
      current ID where possible, and resets scope to Side to move, selections, review markers, and
      passive completion measurement.
- [ ] Score strip displays committed total score, attempts, exact-set accuracy, current streak, and
      best streak from backend responses.
- [ ] Statistics view includes average and most recent passive completion duration without implying
      a target, bonus, ranking, or countdown.
- [ ] History lists committed attempts with puzzle ID, scope, result/point, category discrepancies,
      duration, and submission timestamp in stable order.
- [ ] Refresh and application restart reload progress from the backend rather than browser storage.
- [ ] Statistics/history/navigation failures display recoverable errors without zeroing prior data,
      fabricating progress, or discarding a current unsubmitted answer.

**Technical Details:**

**Database Changes (if any):**

- None; consumes BCK-002 queries.

**API Endpoints (if any):**

- Consumes `GET /api/v1/puzzles/next`, `GET /api/v1/stats`, and `GET /api/v1/attempts`.

**Frontend Components (if any):**

- Component Name: Next-puzzle controller, score strip, statistics view, history list
- Props: Backend public puzzle, stats, and attempt-history DTOs
- State: Loading/error snapshots and current committed progress view
- Styling: Simple desktop-first layout with semantic table/list and keyboard-accessible controls

**Dependencies:**

- Blocks: EPIC-05-HARDENING-HANDOFF
- Is Blocked By: UI-001, UI-003, and BCK-004
- Related To: BCK-002 aggregate/history behavior

**Testing Requirements:**

- Unit Tests: Statistics formatting, history rendering, duration labels, and reset state.
- Integration Tests: API refresh/restart data, next-puzzle exclusion, and read failures.
- E2E Tests: Complete two-puzzle flow, score/streak updates, history, refresh, restart, and recovery
  without data loss.
- Manual Testing: Verify statistics remain concise and do not create timing pressure.

**Related Sections from Blueprint:**

- Continue Training and Review Progress flow
- Component 7: Browser Training UI
- API Design: puzzle, stats, and history routes
- Business Metrics

**Implementation Notes:**

- Do not duplicate authoritative attempt history in localStorage.
- Prefer derived display formatting over storing alternate aggregate values.
- Keep advanced charts, filtering, adaptive selection, and mobile-specific views out of scope.

**Definition of Done:**

- [ ] Navigation, statistics, and history views are implemented and reviewed.
- [ ] Unit, integration, and browser workflow tests pass.
- [ ] Progress-display and recovery behavior are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.
