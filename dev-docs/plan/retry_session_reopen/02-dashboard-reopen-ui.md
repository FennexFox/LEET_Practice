# Phase 02: Add reopen controls and verify the workflow

## Goal

- Make delayed result entry obvious and usable from the main dashboard.

## Scope

- Add a `기존 재풀이 결과 입력` section with a session ID/code form.
- Fetch and render recent generated sessions with date, title, question count,
  session ID, and submission state.
- Link each recent session to the server-rendered result-entry page.
- Document the delayed-entry workflow and complete automated/manual checks.

## Non-goals

- Editing result-entry grading or retry-selection semantics.
- Browser-side access to manifest contents or answer keys.
- Deleting or archiving retry sessions from the dashboard.

## Affected files

- `tools/build_tagging_dashboard.py`
- `tests/test_build_tagging_dashboard.py`
- `README.md`
- Phase-plan outcome files

## Implementation steps

1. Add accessible lookup markup and explanatory copy near the PDF builder.
2. Add client-side form navigation using an encoded session query.
3. Load recent-session summaries and render them with safe DOM APIs.
4. Refresh recent history after a PDF is generated.
5. Update dashboard tests and README instructions.
6. Run focused/full tests and an HTTP smoke test across a server restart.

## Acceptance criteria

- A learner can leave the generation page and later reopen entry using the ID
  printed in the PDF or its final 10 characters.
- Recent sessions remain discoverable after restarting the local server.
- The history UI degrades clearly when the HTML file is opened without the
  live server.
- User-controlled labels are inserted as text, never raw HTML.

## Validation commands

- python -m pytest -q

## Manual smoke tests

- Start the local dashboard server, fetch the recent-session API, and open a result page by full session ID and short code.

## Rollback risks

- Static dashboard snapshots cannot serve the session API; the UI must explain
  that reopening requires the local dashboard server.

## Progress

- Added a labeled session lookup form for full IDs and final 10-character
  codes, with explicit static-snapshot fallback behavior.
- Added safe DOM rendering for recent session summaries and server-side result
  links, plus automatic refresh after PDF generation.
- Regenerated the tracked dashboard snapshot and documented delayed entry,
  restart persistence, manifest retention, and API privacy boundaries.
- Added dashboard markup, accessibility, static-mode, and API integration
  regression checks.

## Decision log

- Keep history read-only and bounded; editing happens only on the existing
  result-entry page.
- Build result links from the server-validated session ID in JavaScript rather
  than trusting an arbitrary URL value from the response.
- Keep the full session ID visible in recent history so an ambiguous short code
  always has a direct recovery path.

## Outcomes / Retrospective

- Focused dashboard validation: 6 tests passed before the final static-mode
  guard; its targeted checks also passed after regeneration.
- Full regression validation: 168 tests passed.
- HTTP smoke tests across two separate server processes returned three sessions
  and HTTP 200 for both full-ID and short-code result pages on each process.
- The registered browser-testing skill instructions were unavailable locally,
  so validation used generated-HTML assertions and live HTTP requests.
- `git diff --check` passed; only repository line-ending warnings remain.
