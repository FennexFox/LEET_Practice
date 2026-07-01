# Phase 04: Validation and documentation

## Goal

- Validate issue #2 and document the draft/correction workflow.

## Scope

- Run full tests and CLI smoke test.
- Update user-facing docs.
- Update phase outcomes.

## Non-goals

- No PR publishing unless separately requested.

## Affected files

- `docs/verification-workbench.md`
- `dev-docs/plan/issue_2/*.md`

## Implementation steps

- Document raw OCR -> draft -> cleanup suggestions -> human verification.
- Run validation commands.
- Commit issue #2 changes.

## Acceptance criteria

- Tests pass.
- Docs describe optional backends and safety boundary.

## Validation commands

- `uv run --extra dev python -m pytest`
- `uv run leet-practice review-crops --help`

## Manual smoke tests

- CLI help displays normally.

## Rollback risks

- Docs-only phase after code is validated.

## Progress

- Completed.

## Decision log

- Use `uv run --extra dev python -m pytest` as the repository validation command
  in this Windows environment.

## Outcomes / Retrospective

- Updated docs for OCR draft prefill, optional local cleanup flags, and the
  raw-OCR-to-canonical boundary.
