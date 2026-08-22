# Graph Report - .  (2026-08-10)

## Corpus Check
- Corpus is ~15,318 words - fits in a single context window. You may not need a graph.

## Summary
- 41 nodes · 79 edges · 6 communities detected
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.78)
- Token cost: 27,400 input · 11,800 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Rules and Catalog Architecture|Rules and Catalog Architecture]]
- [[_COMMUNITY_Authoritative Training Backend|Authoritative Training Backend]]
- [[_COMMUNITY_Foundation and Catalog Tickets|Foundation and Catalog Tickets]]
- [[_COMMUNITY_Backend and UI Tickets|Backend and UI Tickets]]
- [[_COMMUNITY_Accessible Delivery and Handoff|Accessible Delivery and Handoff]]
- [[_COMMUNITY_Product Design Plan|Product Design Plan]]

## God Nodes (most connected - your core abstractions)
1. `BCK-004 Flask API, Local Security, and Backend Integration Tests` - 9 edges
2. `Puzzle Catalog` - 6 edges
3. `Training Service` - 6 edges
4. `Progress Repository` - 6 edges
5. `Flask Web Layer` - 6 edges
6. `FND-003 Implement Piece-Safety Classification, Scoring, and Golden Tests` - 6 edges
7. `CAT-001 Define the Versioned Puzzle Catalog Contract and Validator` - 6 edges
8. `BCK-003 Training Submission and Feedback Service` - 6 edges
9. `Chess Classification Domain` - 5 edges
10. `EPIC-03 Durable Training Backend` - 5 edges

## Surprising Connections (you probably didn't know these)
- `UI-004 Puzzle Navigation, Statistics, and History Views` --shares_data_with--> `Progress Repository`  [INFERRED]
  design/EPIC-04-INTERACTIVE-BOARD.md → design/blueprint.md
- `FND-003 Implement Piece-Safety Classification, Scoring, and Golden Tests` --implements--> `Exact Hanging-Set Scoring`  [EXTRACTED]
  design/EPIC-01-FOUNDATION-RULES.md → design/blueprint.md
- `FND-003 Implement Piece-Safety Classification, Scoring, and Golden Tests` --implements--> `python-chess Pin-Agnostic Attack Maps`  [EXTRACTED]
  design/EPIC-01-FOUNDATION-RULES.md → design/blueprint.md
- `UI-001 Accessible Chessboard and Application Shell` --implements--> `Custom Accessible Selection Board`  [EXTRACTED]
  design/EPIC-04-INTERACTIVE-BOARD.md → design/blueprint.md
- `CAT-002 Implement the Streaming Lichess Curation Pipeline` --implements--> `Curation Pipeline`  [EXTRACTED]
  design/EPIC-02-PUZZLE-CATALOG.md → design/blueprint.md

## Hyperedges (group relationships)
- **Build-Time Catalog Curation Flow** — blueprint_curation_pipeline, blueprint_chess_classification_domain, blueprint_puzzle_catalog_model, blueprint_immutable_catalog_precomputed_answers [EXTRACTED 1.00]
- **Authoritative Submission Transaction** — blueprint_browser_training_ui, blueprint_flask_web_layer, blueprint_training_service, blueprint_progress_repository, blueprint_attempt_model [EXTRACTED 1.00]
- **Five-Epic Delivery Chain** — hanging_piece_trainer_tickets_epic_01_foundation_rules, hanging_piece_trainer_tickets_epic_02_puzzle_catalog, hanging_piece_trainer_tickets_epic_03_training_backend, hanging_piece_trainer_tickets_epic_04_interactive_board, hanging_piece_trainer_tickets_epic_05_hardening_handoff [EXTRACTED 1.00]

## Communities

### Community 0 - "Rules and Catalog Architecture"
Cohesion: 0.31
Nodes (9): Chess Classification Domain, Curation Pipeline, Immutable Catalog with Precomputed Answers, python-chess Pin-Agnostic Attack Maps, Puzzle Catalog, PuzzleCatalog Data Model, SQLite as Progress Authority, EPIC-01 Foundation & Chess Rules (+1 more)

### Community 1 - "Authoritative Training Backend"
Cohesion: 0.28
Nodes (9): Attempt Data Model, Exact Hanging-Set Scoring, Flask and Server-Rendered Shell, Flask Web Layer, Loopback-Only Same-Origin Runtime, Progress Repository, Puzzle Data Model, Training Service (+1 more)

### Community 2 - "Foundation and Catalog Tickets"
Cohesion: 0.57
Nodes (7): FND-001 Bootstrap Python Project and Developer Tooling, FND-002 Implement Chess Reconstruction and Domain Contracts, FND-003 Implement Piece-Safety Classification, Scoring, and Golden Tests, CAT-001 Define the Versioned Puzzle Catalog Contract and Validator, CAT-002 Implement the Streaming Lichess Curation Pipeline, CAT-003 Generate and Verify the 100-Puzzle Training Catalog, BCK-001 Runtime Puzzle Catalog and Selection Service

### Community 3 - "Backend and UI Tickets"
Cohesion: 0.62
Nodes (7): BCK-002 SQLite Attempts, Migrations, and Derived Statistics, BCK-003 Training Submission and Feedback Service, BCK-004 Flask API, Local Security, and Backend Integration Tests, UI-001 Accessible Chessboard and Application Shell, UI-002 Scope and Classification Selection State, UI-003 Submission and Visual Review Feedback, UI-004 Puzzle Navigation, Statistics, and History Views

### Community 4 - "Accessible Delivery and Handoff"
Cohesion: 0.33
Nodes (7): Browser Training UI, Custom Accessible Selection Board, HND-001 Browser, Offline, and Accessibility Validation, HND-002 Setup, Operations, Recovery, and Provenance Documentation, HND-003 Final P0 Acceptance and Release Handoff, EPIC-04 Interactive Board & Feedback, EPIC-05 Hardening & Handoff

### Community 5 - "Product Design Plan"
Cohesion: 1.0
Nodes (2): Hanging Piece Trainer, Hanging Piece Trainer Implementation Plan

## Knowledge Gaps
- **5 isolated node(s):** `Hanging Piece Trainer`, `Loopback-Only Same-Origin Runtime`, `Flask and Server-Rendered Shell`, `Hanging Piece Trainer Implementation Plan`, `EPIC-05 Hardening & Handoff`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Product Design Plan`** (2 nodes): `Hanging Piece Trainer`, `Hanging Piece Trainer Implementation Plan`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BCK-004 Flask API, Local Security, and Backend Integration Tests` connect `Backend and UI Tickets` to `Authoritative Training Backend`, `Foundation and Catalog Tickets`, `Accessible Delivery and Handoff`?**
  _High betweenness centrality (0.192) - this node is a cross-community bridge._
- **Why does `Flask Web Layer` connect `Authoritative Training Backend` to `Backend and UI Tickets`, `Accessible Delivery and Handoff`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Why does `Training Service` connect `Authoritative Training Backend` to `Rules and Catalog Architecture`, `Backend and UI Tickets`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **What connects `Hanging Piece Trainer`, `Loopback-Only Same-Origin Runtime`, `Flask and Server-Rendered Shell` to the rest of the system?**
  _5 weakly-connected nodes found - possible documentation gaps or missing edges._