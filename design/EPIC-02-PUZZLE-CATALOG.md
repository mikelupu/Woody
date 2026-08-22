### EPIC-02-PUZZLE-CATALOG: Puzzle Curation & Catalog

**Epic Details:**
Build a deterministic, build-time transformation from an explicitly supplied Lichess puzzle
snapshot to a versioned immutable catalog of exactly 100 validated middlegame positions. The
catalog retains provenance and private White/Black answers while runtime remains fully offline.

---

- [ ] **CAT-001: Define the Versioned Puzzle Catalog Contract and Validator**

**Issue Type:** Task

**Summary:** Define the versioned puzzle catalog contract and validator

**Effort Estimate:** Medium (for reference only)

**Labels:** data, catalog, schema, validation, backend

**Parent Epic:** EPIC-02-PUZZLE-CATALOG (Puzzle Curation & Catalog)

**Description:**
Define the canonical JSON catalog structure and a framework-independent validator. The contract
must preserve source and rules provenance, normalize puzzle answers, detect accidental changes, and
support safe loading by both curation tests and the runtime catalog adapter.

**Acceptance Criteria:**

- [ ] The catalog contract includes schema version, rules version, source URL/name/date/checksum,
      deterministic selection seed, catalog checksum, and exactly 100 puzzle records.
- [ ] Each puzzle records stable puzzle ID, source URL, source FEN, first UCI move, presented FEN,
      side to move, retained public metadata, and private White/Black undefended/hanging sets.
- [ ] Validation rejects unsupported versions, duplicate puzzle IDs, invalid themes/FEN/squares,
      answer squares with the wrong piece color, kings in answer sets, and hanging sets that are not
      subsets of undefended sets.
- [ ] Canonical serialization has deterministic key and set ordering so identical logical content
      produces byte-stable JSON and checksum results.
- [ ] Validation errors identify the record and violated invariant without dumping the entire
      catalog or silently repairing content.

**Technical Details:**

**Database Changes (if any):**

- None; puzzle content is immutable JSON rather than SQLite data.

**API Endpoints (if any):**

- None.

**Frontend Components (if any):**

- None.

**Dependencies:**

- Blocks: CAT-002, CAT-003, and runtime Puzzle Catalog work
- Is Blocked By: FND-002 and FND-003
- Related To: Blueprint PuzzleCatalog and Puzzle data models

**Testing Requirements:**

- Unit Tests: Valid catalog, every schema invariant, canonical ordering, checksum calculation, and
  stable validation errors.
- Integration Tests: Recompute representative puzzle answers using the shared domain classifier.
- E2E Tests: None.
- Manual Testing: Review one serialized record for provenance and human readability.

**Related Sections from Blueprint:**

- Component 3: Puzzle Catalog
- Data Models: PuzzleCatalog and Puzzle
- Relationships and Invariants
- Decision 4: Immutable Catalog with Precomputed Answers

**Implementation Notes:**

- Keep the catalog contract independent from Flask and SQLite.
- Treat expected answers as backend-private application content, not public API fields.
- Use explicit version constants rather than inferred compatibility.

**Definition of Done:**

- [ ] Catalog contract, serializer, checksum logic, and validator are implemented and reviewed.
- [ ] Unit and integration tests pass.
- [ ] Contract and versioning behavior are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **CAT-002: Implement the Streaming Lichess Curation Pipeline**

**Issue Type:** Task

**Summary:** Implement the streaming Lichess curation pipeline

**Effort Estimate:** High (for reference only)

**Labels:** data, curation, lichess, streaming, chess-rules

**Parent Epic:** EPIC-02-PUZZLE-CATALOG (Puzzle Curation & Catalog)

**Description:**
Implement a reproducible command that streams a local Lichess puzzle snapshot, reconstructs and
classifies eligible records, selects a deterministic subset, and writes a candidate catalog safely.
The command must bound memory usage and must never acquire source data or overwrite a good catalog
implicitly.

**Acceptance Criteria:**

- [ ] The command accepts explicit source/output paths, a deterministic seed, and source metadata;
      it supports documented compressed `.zst` and decompressed CSV inputs.
- [ ] Input is processed as a stream without loading the full Lichess database into memory.
- [ ] Records must be standard chess, contain the exact `middlegame` theme token, reconstruct by
      applying the first legal UCI move, and produce a valid presented position.
- [ ] White and Black answers are computed through the shared classifier; candidates require at
      least one hanging piece for the presented side to move.
- [ ] Selection is deterministic for identical source bytes, rules version, and seed, and duplicate
      puzzle IDs cannot enter the candidate set.
- [ ] Malformed/ineligible records are counted with bounded diagnostics; systemic input/schema
      failure stops rather than being mistaken for ordinary skipped records.
- [ ] Fewer than 100 eligible records, validation failure, interruption, or output error leaves any
      existing destination unchanged; successful replacement is atomic.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- None; this is an operator-invoked build command.

**Frontend Components (if any):**

- None.

**Dependencies:**

- Blocks: CAT-003
- Is Blocked By: CAT-001, FND-002, and FND-003
- Related To: Lichess source-format documentation

**Testing Requirements:**

- Unit Tests: CSV parsing, exact theme matching, skip/fail classification, deterministic sampling,
  duplicate handling, and bounded diagnostics.
- Integration Tests: Compressed and decompressed fixtures, reconstruction/classification integration,
  insufficient-record failure, and atomic output replacement.
- E2E Tests: None.
- Manual Testing: Run against a bounded real-source sample supplied by the operator.

**Related Sections from Blueprint:**

- Component 1: Curation Pipeline
- Data Flow and Trust Boundaries
- Decision 4: Immutable Catalog with Precomputed Answers
- Testing Strategy: Curation tests

**Implementation Notes:**

- Source download is outside this command and requires an explicit operator action.
- Keep curation dependencies in an optional group where practical so runtime stays minimal.
- Do not store the large source dataset or temporary decompressed files in version control.

**Definition of Done:**

- [ ] Streaming curation command is implemented and reviewed.
- [ ] Unit and integration tests pass for compressed/decompressed and failure paths.
- [ ] Command usage, source expectations, and diagnostics are documented.
- [ ] No linter or formatting errors remain.
- [ ] Acceptance criteria are met.

---

- [ ] **CAT-003: Generate and Verify the 100-Puzzle Training Catalog**

**Issue Type:** Task

**Summary:** Generate and verify the 100-puzzle training catalog

**Effort Estimate:** Medium (for reference only)

**Labels:** data, catalog, lichess, validation, acceptance-testing

**Parent Epic:** EPIC-02-PUZZLE-CATALOG (Puzzle Curation & Catalog)

**Description:**
Use an operator-supplied or explicitly authorized Lichess snapshot to generate the shipped V1
catalog, review its provenance, and prove every stored answer against the pinned rules version. The
committed artifact becomes the only runtime puzzle source for the first release.

**Acceptance Criteria:**

- [ ] The source acquisition method, URL, snapshot date, checksum, selection seed, catalog schema,
      and rules version are recorded with the generated artifact.
- [ ] The committed catalog contains exactly 100 unique standard-chess records whose themes include
      exact `middlegame` and whose presented side has at least one hanging piece.
- [ ] Every source FEN plus first UCI move reconstructs exactly to its stored presented FEN.
- [ ] Independent acceptance validation recomputes White and Black undefended/hanging sets for all
      100 records and matches the stored normalized answers.
- [ ] Re-running curation with identical inputs reproduces byte-identical canonical catalog content
      and checksum.
- [ ] No source database, temporary decompressed file, or unlicensed runtime asset is committed.

**Technical Details:**

**Database Changes (if any):**

- None.

**API Endpoints (if any):**

- None.

**Frontend Components (if any):**

- None.

**Dependencies:**

- Blocks: EPIC-03-TRAINING-BACKEND
- Is Blocked By: CAT-001, CAT-002, and availability/authorization of the Lichess source snapshot
- Related To: Lichess open database provenance and project license inventory

**Testing Requirements:**

- Unit Tests: None beyond reused catalog/domain validators.
- Integration Tests: Full-catalog reconstruction, classification recomputation, uniqueness, count,
  checksum, and deterministic regeneration.
- E2E Tests: None.
- Manual Testing: Review a representative White-to-move and Black-to-move sample and verify source
  links/provenance metadata.

**Related Sections from Blueprint:**

- Component 1: Curation Pipeline
- Component 3: Puzzle Catalog
- Decision 4: Immutable Catalog with Precomputed Answers
- Phase 2: Dataset Curation and Catalog

**Implementation Notes:**

- Do not fetch or replace the source snapshot without explicit operator authorization.
- Expected answers remain in backend-only catalog content and must not be copied into browser assets.
- This ticket produces a durable data artifact, not new classification semantics.

**Definition of Done:**

- [ ] V1 catalog is generated, reviewed, and committed.
- [ ] Full-catalog acceptance validation passes.
- [ ] Provenance and deterministic regeneration are documented.
- [ ] No linter, formatting, or catalog-validation errors remain.
- [ ] Acceptance criteria are met.
