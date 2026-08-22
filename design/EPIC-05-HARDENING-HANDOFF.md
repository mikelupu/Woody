### EPIC-05-HARDENING-HANDOFF: Hardening & Handoff

**Epic Details:**
Validate the complete application across browser, backend, persistence, catalog, accessibility, and
offline boundaries. Produce durable operating documentation, provenance, and P0 acceptance evidence
without adding features or timing targets.

---

- [ ] **HND-001: Complete Browser, Offline, and Accessibility Validation**

**Issue Type:** Task

**Summary:** Complete browser, offline, and accessibility validation

**Effort Estimate:** High (for reference only)

**Labels:** testing, e2e, accessibility, offline, security

**Parent Epic:** EPIC-05-HARDENING-HANDOFF (Hardening & Handoff)

**Description:**
Build and run the cross-layer browser suite that proves the local training experience works with
the real Flask API and SQLite persistence. The suite must cover the workflows and accessibility
semantics that component tests cannot establish and must fail on any external runtime request.

**Acceptance Criteria:**

- [ ] Browser automation starts the application through the supported local entrypoint and exercises
      real catalog, API, and isolated SQLite test state.
- [ ] Tests cover White- and Black-to-move orientation plus Side to move, White, Black, and Both
      scopes, including per-puzzle default reset and unchanged orientation.
- [ ] Pointer and keyboard workflows cover valid/invalid selection, hanging/undefended invariants,
      empty submission, exact result, misses, extras, overlapping category outcomes, and answer lock.
- [ ] Positive ticks, dedicated miss color plus non-color cue, negative markers, legend, text
      equivalents, focus movement, accessible names, and visible focus are asserted.
- [ ] Tests prove duplicate-click idempotency, recoverable submission failure with preserved answer,
      committed statistics/history, next-puzzle reset, refresh, and application restart persistence.
- [ ] A network allowlist fails the suite on every non-loopback runtime request, including scripts,
      styles, fonts, telemetry, or data.
- [ ] Tests use isolated temporary progress state and never read or overwrite the user's database.

**Technical Details:**

**Database Changes (if any):**

- None; use isolated BCK-002 schemas/fixtures.

**API Endpoints (if any):**

- Exercises all `/api/v1` endpoints through the browser rather than mocks for acceptance paths.

**Frontend Components (if any):**

- Validates the complete application shell, board, controls, markers, feedback, statistics, and
  history.

**Dependencies:**

- Blocks: HND-003
- Is Blocked By: BCK-004 and UI-001 through UI-004
- Related To: HND-002 troubleshooting documentation

**Testing Requirements:**

- Unit Tests: Helper/fixture behavior where material.
- Integration Tests: Local application process, isolated database, and network allowlist harness.
- E2E Tests: Every acceptance criterion above.
- Manual Testing: Screen-reader/keyboard spot check for behavior not reliably covered by automation.

**Related Sections from Blueprint:**

- Testing Strategy: Browser tests
- Security Considerations
- Success Metrics
- Phase 5: Hardening and Handoff

**Implementation Notes:**

- Pin browser-test tooling in the development dependency group.
- Keep the test server loopback-only and use task-scoped temporary storage.
- Do not add performance assertions or completion-time expectations.

**Definition of Done:**

- [ ] Browser/offline/accessibility suite is implemented and reviewed.
- [ ] Automated suite and manual accessibility spot check pass.
- [ ] Network allowlist and isolated-state behavior are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **HND-002: Document Setup, Operations, Recovery, and Provenance**

**Issue Type:** Task

**Summary:** Document setup, operations, recovery, and provenance

**Effort Estimate:** Medium (for reference only)

**Labels:** documentation, operations, recovery, licensing, provenance

**Parent Epic:** EPIC-05-HARDENING-HANDOFF (Hardening & Handoff)

**Description:**
Create the user and developer documentation needed to install, run, test, maintain, and recover the
local application. Record dependency and puzzle-source provenance so the fixed catalog and offline
runtime are understandable and reproducible.

**Acceptance Criteria:**

- [ ] README documents prerequisites, `uv`/Make setup, normal and development startup, local URL,
      stop procedure, canonical checks, and the single-user loopback boundary.
- [ ] User guidance explains all four scopes, both classification categories, scoring/streak rules,
      passive completion statistics, visual marker legend, and keyboard operation.
- [ ] Operations guidance identifies the SQLite path and provides stopped-app backup, restore,
      explicit reset, corruption/unsupported-schema recovery, and troubleshooting procedures that
      never imply silent deletion.
- [ ] Curation guidance documents source acquisition as an explicit operator action, accepted input
      formats, checksum/provenance inputs, deterministic seed, generation, validation, and catalog
      replacement behavior.
- [ ] A provenance/license inventory records runtime/development dependencies, Lichess source URL
      and snapshot/checksum, catalog generation details, and any bundled glyph/asset considerations.
- [ ] Documentation clearly states offline/runtime-network behavior, no accounts/cloud sync,
      desktop-first scope, excluded features, and absence of timing targets.
- [ ] Every documented command and recovery procedure is exercised against a clean or isolated
      environment before approval.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- Document local health diagnostics and user-safe errors; do not publish a remote-service contract.

**Frontend Components (if any):**

- Document controls, legend, accessible feedback, and supported desktop context.

**Dependencies:**

- Blocks: HND-003
- Is Blocked By: CAT-003, BCK-004, and UI-001 through UI-004
- Related To: HND-001 observed validation/recovery behavior

**Testing Requirements:**

- Unit Tests: None.
- Integration Tests: Scripted or checklist validation of every documented command and recovery path.
- E2E Tests: Cross-reference HND-001 user workflows.
- Manual Testing: Follow the README from a clean environment without relying on undocumented steps.

**Related Sections from Blueprint:**

- Deployment Strategy
- Data Recovery
- Dependency Governance
- Related Documentation
- Phase 5: Hardening and Handoff

**Implementation Notes:**

- Keep user instructions concise and separate advanced curation/developer material clearly.
- Do not instruct users to bind the application to a LAN interface.
- Link the approved PRD, blueprint, and ticket bundle for traceability.

**Definition of Done:**

- [ ] User/developer documentation and provenance inventory are written and reviewed.
- [ ] Every documented command and recovery path has been exercised.
- [ ] Links and artifact references resolve.
- [ ] No documentation lint or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **HND-003: Execute Final P0 Acceptance and Release Handoff**

**Issue Type:** Task

**Summary:** Execute final P0 acceptance and release handoff

**Effort Estimate:** Medium (for reference only)

**Labels:** acceptance-testing, release, quality, handoff

**Parent Epic:** EPIC-05-HARDENING-HANDOFF (Hardening & Handoff)

**Description:**
Run the complete validation and PRD P0 acceptance set against the release candidate, record durable
evidence, resolve release-blocking discrepancies through their owning tickets, and prepare the
personal application handoff. This ticket validates scope; it does not add new product behavior.

**Acceptance Criteria:**

- [ ] `make check`, `make test`, and `make test-cov` pass, overall coverage exceeds the repository
      guideline, and critical chess-rule/transaction branches have the required focused coverage.
- [ ] All 100 catalog records pass schema/checksum, reconstruction, uniqueness, eligibility, and
      White/Black answer recomputation validation.
- [ ] Every P0 scenario in the approved PRD is executed against the release candidate and recorded
      with pass/fail evidence and issue references for any remediation.
- [ ] Offline network, loopback binding, debug-off runtime, same-origin mutation, persistence restart,
      backup/restore, corruption behavior, and no-answer-leakage checks pass.
- [ ] Product-owner review confirms four scopes, board orientation, score/streak rules, positive
      ticks, miss treatment, negative markers, text feedback, statistics, and history.
- [ ] Documentation/provenance review passes and no unresolved High-impact or release-blocking defect
      remains.
- [ ] Final handoff records application startup, progress location, known limitations, completed
      scope, validation results, and recommended future work without adding a timing commitment.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- Validate all documented endpoints; introduce no new route.

**Frontend Components (if any):**

- Validate all shipped components; introduce no new component unless tied to an approved defect.

**Dependencies:**

- Blocks: Initial release completion
- Is Blocked By: HND-001, HND-002, and completion of all earlier epic acceptance criteria
- Related To: Approved PRD UAT table and blueprint Success Metrics

**Testing Requirements:**

- Unit Tests: Run full suite; add only defect-focused regression coverage when necessary.
- Integration Tests: Run full backend/catalog/persistence suite.
- E2E Tests: Run HND-001 suite against the release candidate.
- Manual Testing: Execute and record every P0 scenario and product-owner visual review.

**Related Sections from Blueprint:**

- Testing Strategy
- Success Metrics
- Risks & Mitigations
- Phase 5: Hardening and Handoff

**Implementation Notes:**

- Route discovered defects back to the ticket owning the behavior and rerun affected validation.
- Do not waive failed P0 outcomes through documentation alone.
- Keep the handoff local/personal; Jira or GitHub synchronization is a separate workflow.

**Definition of Done:**

- [ ] Full automated validation and catalog acceptance pass.
- [ ] All PRD P0 scenarios and product-owner visual review pass.
- [ ] Documentation and provenance are complete.
- [ ] Release handoff and known limitations are recorded.
- [ ] No unresolved release blocker remains.
- [ ] Acceptance criteria are met.
