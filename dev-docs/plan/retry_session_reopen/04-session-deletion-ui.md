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

- Not started.

## Decision log

- Show one `세션 삭제` action for the entire bundle; result-only correction is
  already supported by resubmission and should not create competing semantics.

## Outcomes / Retrospective

- Not completed yet.
