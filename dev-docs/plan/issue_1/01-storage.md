# Phase 01: Verification state models and storage

## Goal

- Build the verification state model and file storage layer used by both the UI
  and the promotion command.

## Scope

- New verification-domain module for parsing crop suggestions and managing
  `data/verification/<exam_id>/`.
- CLI-accessible initialization path that can turn a `suggestions.json` file
  into a persistent review queue.
- Unit tests for parsing candidate previews, default statuses, autosave shape,
  and accepted draft JSONL writes.

## Non-goals

- No browser UI in this phase.
- No writes to `data/canonical/`.
- No OCR execution or crop generation changes.

## Affected files

- `src/leet_practice/verification.py`
- `src/leet_practice/cli.py`
- `tests/test_verification_storage.py`
- `dev-docs/plan/issue_1/01-storage.md`

## Implementation steps

- Define review status and candidate/draft models.
- Parse crop-suggestion candidates with enough tolerance for existing artifact
  structure.
- Create `data/verification/<exam_id>/crop-review-state.json`.
- Provide functions to update candidate status and write accepted
  `verified_passages.jsonl` / `verified_questions.jsonl`.
- Add CLI command support needed for phase validation.
- Add tests around synthetic suggestion artifacts.

## Acceptance criteria

- Running the init path creates a stable review-state file.
- All candidates default to `unreviewed`.
- Review state preserves suggestion source path and candidate provenance.
- Accepted passage/question drafts can be written as JSONL without touching
  canonical data.

## Validation commands

- `uv run --extra dev python -m pytest`
- If uv is unavailable, `python -m pytest`

## Manual smoke tests

- Run `leet-practice review-crops --help` and confirm the command exists.
- Run the storage init path against a synthetic fixture through tests.

## Rollback risks

- Low risk: new storage files are additive.
- Main rollback concern is CLI command shape; keep command names aligned with
  the issue body.

## Progress

- Completed.

## Decision log

- Use JSON/JSONL storage first; defer SQLite or a larger web framework until the
  review workflow proves stable.
- `uv run pytest` used the wrong global pytest executable in this Windows
  environment; validation uses `uv run --extra dev python -m pytest`.

## Outcomes / Retrospective

- Added verification models, suggestion parsing, review-state persistence,
  accepted draft JSONL writes, CLI initialization path, and storage tests.
