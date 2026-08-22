# Release acceptance record

Date: 2026-08-10

## Automated evidence

- 33 domain, catalog, curation, repository, service, and Flask integration tests pass.
- Branch coverage: 89% (required baseline: greater than 80%).
- Ruff lint and format checks pass.
- All 100 bundled positions pass checksum, uniqueness, source reconstruction, FEN validity,
  side-to-move eligibility, and White/Black answer recomputation.
- Live `/api/v1/health` reports catalog and database ready.
- Live responses include local-only CSP, nosniff, no-referrer, and no-store headers.

## Manual/browser acceptance

The following must be checked in a connected desktop browser before tagging a release:

- White and Black orientations and all four scopes.
- Keyboard board traversal, selection invariants, focus visibility, and announcements.
- Correct, missed, and incorrect hanging-piece markers plus equivalent text.
- Failed submission retry, duplicate activation, refresh, and restart persistence.
- Browser network log contains no non-loopback request.
- Supported-browser Unicode chess glyph rendering and color/contrast review.

The build environment used for this implementation did not expose a controllable browser, so these
visual/manual items are deliberately recorded as pending rather than represented as passed.
