# Phase 01: Discover and resolve retry sessions

## Goal

- Add a safe server-side session index and resolve result pages by durable ID.

## Scope

- Discover and validate retry manifests inside the configured retry output
  root, returning only non-sensitive summary fields.
- Resolve either a complete session ID or an exact 10-hex-character suffix.
- Add a recent-session JSON endpoint and accept `session=` on the result-entry
  route while retaining the legacy `manifest=` query.
- Generate new result-entry URLs with the stable session ID.

## Non-goals

- Changes to retry-result persistence, grading, or completed-question policy.
- Recursive searches outside the retry-PDF output directory.
- Content hashes or renaming existing PDF/manifest files.

## Affected files

- `tools/serve_tagging_dashboard.py`
- `tests/test_build_tagging_dashboard.py`

## Implementation steps

1. Build a validated manifest inventory sorted newest-first.
2. Add exact/full and unique-short-code resolution with clear errors.
3. Enrich summaries with submitted-result status without exposing answers.
4. Add `GET /api/retry-sessions` and session-based result-page routing.
5. Switch newly generated result-entry links to `session=`.
6. Add focused discovery, ambiguity, routing, and response tests.

## Acceptance criteria

- A full ID and its unique final 10 characters resolve to the same manifest.
- Invalid, absent, or ambiguous codes never resolve an arbitrary file.
- Recent-session responses omit selected choices and correct answers.
- Result status is derived from existing saved retry-result files.
- Existing manifest-path result URLs continue to render.

## Validation commands

- python -m pytest -q

## Manual smoke tests

- Start the local dashboard server, fetch the recent-session API, and open a result page by full session ID and short code.

## Rollback risks

- A too-permissive discovery path could expose unrelated JSON or answer keys;
  fixed-root scanning and summary projection contain the risk.

## Progress

- Added fixed-root, non-recursive manifest discovery with schema validation,
  generated-time sorting, and malformed-file isolation.
- Added exact session ID and unique 10-character suffix resolution.
- Added sanitized recent-session summaries with persisted-result counts.
- Added `/api/retry-sessions`, `session=` result routing, and session-based
  result-entry URLs for new PDF bundles.

## Decision log

- Use the existing UUID-backed session ID already printed in the PDF instead
  of adding a second hash identifier.
- Short lookup codes are exactly the final 10 hexadecimal characters.

## Outcomes / Retrospective

- Focused backend validation: 4 tests passed.
- Full regression validation: 167 tests passed.
- Live repository inventory found three valid sessions and returned only the
  intended summary fields.
- `git diff --check` passed; only repository line-ending warnings remain.
