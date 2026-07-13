# Phase 04: Add dashboard deletion controls

## Goal

- Let a learner remove an incorrectly generated retry session directly from
  recent history with an explicit irreversible-action warning.

## Scope

- Add a per-session delete button beside the result-entry link.
- Confirm that the PDF, manifest, and saved result will all be removed.
- Show busy, success, and failure states and refresh recent history after a
  successful deletion.
- Document deletion semantics and regenerate the tracked dashboard snapshot.

## Non-goals

- Deletion from the result-entry page or CLI.
- Multi-select deletion, undo, or a recycle bin.
- Clearing only one submitted answer while keeping the generated session.

## Affected files

- `tools/build_tagging_dashboard.py`
- `docs/tagging-dashboard.html`
- `tests/test_build_tagging_dashboard.py`
- `README.md`
- `docs/data-layout.md`
- Phase-plan outcome files

## Implementation steps

1. Render accessible entry/delete actions with safe DOM APIs.
2. Add an explicit Korean confirmation message and disabled/busy state.
3. Call the exact-ID deletion endpoint and refresh the session list.
4. Add markup/JavaScript regression assertions.
5. Document irreversible bundle deletion and run full/manual validation.

## Acceptance criteria

- Delete is visually distinct from result entry and keyboard accessible.
- Canceling confirmation makes no request and changes no state.
- A successful deletion removes the item from recent history.
- A failed request leaves the item usable and announces the server error.
- The confirmation accurately names every deleted artifact.

## Validation commands

- python -m pytest -q

## Manual smoke tests

- Delete a synthetic session from the live dashboard, verify the recent list
  refreshes, and verify a canceled deletion leaves the session unchanged.

## Rollback risks

- A vague confirmation could cause accidental data loss; wording and danger
  styling must make scope and irreversibility clear.

## Progress

- Renamed the history area to `기존 재풀이 세션 관리` and added an explicit
  permanent-deletion warning covering the PDF, manifest, and saved result.
- Added a danger-styled, accessible per-session button with native confirmation,
  busy state, server error recovery, and cleanup-pending messaging.
- Added full-ID deletion beside the lookup field so sessions older than the
  bounded recent list remain manageable, and included the unique ID in every
  destructive confirmation and accessibility label.
- Refactored recent-session and retry-status loading so deletion refreshes both
  history and recommendation eligibility, including removal of stale selections.
- Invalidated cached retry outcomes on refresh failure and moved focus to the
  visibly focused live status after successful deletion.
- Locked default retry selection while status history is unavailable, unless
  the learner explicitly opts into completed questions.
- Documented complete-bundle deletion, result-status recalculation, and the
  resubmission alternative for answer-entry mistakes.
- Regenerated the tracked dashboard snapshot and expanded regression assertions.

## Decision log

- Show one `세션 삭제` action for the entire bundle; result-only correction is
  already supported by resubmission and should not create competing semantics.
- Use the browser's native confirmation dialog for this rare destructive action
  so cancel, keyboard focus, and blocking behavior stay platform-standard.
- Refresh both session history and retry statuses after deletion because a
  removed submitted result can reveal an older latest outcome.
- Keep short codes valid for opening sessions but require the full ID for the
  typed deletion action and destructive server contract.

## Outcomes / Retrospective

- Focused dashboard/deletion validation: 8 tests passed, including live HTTP
  mappings for success, invalid confirmation, missing sessions, and conflicts.
- Full regression validation: 174 tests passed.
- Generated dashboard JavaScript passed `node --check`.
- Live server smoke returned HTTP 200 with three existing sessions and included
  the management heading, permanent warning, DELETE request, and status refresh.
- The registered browser-control skill file was unavailable, so interactive
  confirm/cancel clicking could not be automated. The remaining local check is
  to cancel once and confirm the row stays, then delete a disposable session.
- `git diff --check` passed; only repository line-ending warnings remain.
