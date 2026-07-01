# Phase 03: Review UX integration

## Goal

- Expose OCR draft metadata and explicit draft reapplication in the workbench.

## Scope

- Show prefill warnings/correction steps near editable fields.
- Add `Apply OCR draft` action.
- Add endpoint to reapply draft for a candidate.

## Non-goals

- No side-by-side diff UI in this issue.

## Affected files

- `src/leet_practice/verification.py`
- `tests/test_verification_workbench.py`
- `dev-docs/plan/issue_2/03-ux-integration.md`

## Implementation steps

- Add API endpoint for draft reapplication.
- Add UI button and metadata panel.
- Ensure normal load/autosave does not overwrite edits.

## Acceptance criteria

- Existing edits survive reload.
- Draft reapplication is explicit.
- Warnings are visible in the UI.

## Validation commands

- `uv run --extra dev python -m pytest`

## Manual smoke tests

- Local workbench page can render draft metadata and call the reapply endpoint.

## Rollback risks

- UI is inline HTML/JS; keep changes scoped and test visible markers.

## Progress

- Completed.

## Decision log

- Draft reapplication uses a dedicated endpoint and button; normal autosave does
  not overwrite user edits with draft data.

## Outcomes / Retrospective

- Added draft warning/correction-step display, `Apply OCR draft`, and endpoint
  tests for explicit reapplication.
