# Phase 02: Attempt review models and storage

## Goal

- Implement attempt-review data models, grading, per-question review storage, and file-based feedback export/import helpers.

## Scope

- New models for attempt records, grading, user self-review, assistant feedback, and user resolution.
- Storage helpers for `data/attempts/<attempt_id>.json` and `data/reviews/<attempt_id>/qXXX.review.json`.
- Answer-key loading with authoritative `answer_key.json`, `questions.jsonl` fallback, and disagreement detection.
- Assistant feedback import that never overwrites `user_self_review`.

## Non-goals

- No direct ChatGPT/OpenAI API integration.
- No final taxonomy synthesis.
- No OCR verification changes.

## Affected files

- `src/leet_practice/models.py`
- `src/leet_practice/attempt_review.py`
- `tests/test_attempt_review_storage.py`

## Implementation steps

- Add new attempt-review Pydantic models while leaving legacy `Review` compatible.
- Implement read/write helpers and validation errors.
- Implement attempt grading from answer strings or stored answer maps.
- Implement pending feedback bundle export and assistant feedback import.
- Add storage-level tests.

## Acceptance criteria

- Attempt records store selected answers separately from canonical question data.
- Grading identifies wrong questions.
- Review files keep user, assistant, and resolution fields separate.
- Assistant feedback import does not overwrite user self-review.
- Provisional tags are stored only under assistant feedback.

## Validation commands

- python -m pytest

## Manual smoke tests

- Create a temporary attempt record and review files through tests.

## Rollback risks

- Moderate. New model names must not break imports or legacy tests.

## Progress

- Completed new v1 attempt-review models in `models.py`.
- Added `attempt_review.py` storage, grading, feedback export, feedback import, and review mutation helpers.
- Added storage tests for answer-key precedence, fallback, disagreement, wrong-answer review files, assistant import preservation, and feedback bundle shape.

## Decision log

- `answer_key.json` remains authoritative even when `questions.jsonl` has additional context.
- Review files are created for wrong questions by default; correct question review creation is available internally through `include_correct`.
- Feedback export includes grading, canonical question context, and user self-review; it intentionally omits `user_resolution`.

## Outcomes / Retrospective

- Completed. Targeted and full test suites passed.
