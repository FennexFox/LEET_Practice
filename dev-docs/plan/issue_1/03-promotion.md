# Phase 03: Canonical promotion validation

## Goal

- Implement explicit validation and promotion from verification drafts to
  canonical JSONL files.

## Scope

- Add `promote-verified --exam-id <exam_id>`.
- Validate accepted drafts before writing canonical files.
- Write or replace canonical `passages.jsonl` and `questions.jsonl` only after a
  successful validation pass.
- Add tests for valid promotion and validation failures.

## Non-goals

- No grading or attempt workflow.
- No merging with remote/shared canonical datasets.
- No answer-key OCR implementation.

## Affected files

- `src/leet_practice/verification.py`
- `src/leet_practice/cli.py`
- `tests/test_promote_verified.py`
- `dev-docs/plan/issue_1/03-promotion.md`

## Implementation steps

- Load verification drafts for an exam.
- Validate unique question numbers, complete 1-5 choices, valid correct answers,
  valid passage links, and source provenance.
- Write canonical JSONL files atomically enough for local use.
- Add command output summarizing promoted record counts.

## Acceptance criteria

- Invalid drafts fail before canonical files are modified.
- Valid drafts promote to `data/canonical/<exam_id>/passages.jsonl` and
  `questions.jsonl`.
- Promotion remains explicit and separate from `review-crops` autosave.

## Validation commands

- `uv run --extra dev python -m pytest`
- If uv is unavailable, `python -m pytest`

## Manual smoke tests

- Run `leet-practice promote-verified --help`.
- Promote a synthetic verification directory in tests and inspect output files.

## Rollback risks

- Medium risk: overwriting existing canonical files. Use validation first and
  deterministic writes; keep future merge behavior out of this issue.

## Progress

- Completed.

## Decision log

- Canonical question rows preserve source provenance by writing verified draft
  rows rather than narrowing them to the current `Question` model.

## Outcomes / Retrospective

- Added explicit promotion validation and canonical JSONL writes. Tests cover
  successful promotion and failure before canonical writes on invalid drafts.
