# Phase 04: Tests docs and validation

## Goal

- Finish docs, focused tests, and repository validation for issue #10.

## Scope

- Update documentation for the attempt-review workflow.
- Run targeted and full test validation.
- Record phase outcomes.

## Non-goals

- No commit or PR unless explicitly requested.

## Affected files

- `docs/data-layout.md`
- `README.md`
- `dev-docs/plan/issue_10/*.md`
- Relevant test files.

## Implementation steps

- Add documentation for storage layout and command flow.
- Run `python -m pytest`.
- Run CLI help smoke test when possible.
- Inspect `git status --short`.

## Acceptance criteria

- Tests pass.
- Docs describe the v1 layout and file handoff.
- Final summary identifies changed files and any residual risk.

## Validation commands

- python -m pytest

## Manual smoke tests

- `leet-practice attempt-review --help`
- `leet-practice attempt-review serve --help`

## Rollback risks

- Low. Docs and tests should be easy to revert independently.

## Progress

- Added `docs/attempt-review.md`.
- Updated `README.md` and `docs/data-layout.md` with the v1 workflow and storage layout.
- Ran targeted tests and full test suite.
- Ran CLI help smoke checks.

## Decision log

- The docs call out that assistant feedback tags are provisional until user resolution.
- The docs keep attempt review separate from OCR verification.

## Outcomes / Retrospective

- Completed. `uv run --extra dev python -m pytest` passed with 98 tests.
- `uv run --extra dev leet-practice attempt-review --help` passed.
- `uv run --extra dev leet-practice attempt-review serve --help` passed.
