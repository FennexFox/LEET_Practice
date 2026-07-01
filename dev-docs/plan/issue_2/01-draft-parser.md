# Phase 01: Deterministic OCR draft parser

## Goal

- Generate structured OCR draft fields from `raw_ocr_text`.

## Scope

- Passage body prefill from raw OCR.
- Question stem/choice parsing for circled and numeric choice markers.
- Draft metadata for source, warnings, and correction steps.

## Non-goals

- No ML/spacing/morphology backends in this phase.
- No canonical writes.

## Affected files

- `src/leet_practice/verification.py`
- `tests/test_ocr_prefill.py`
- `dev-docs/plan/issue_2/01-draft-parser.md`

## Implementation steps

- Add draft metadata fields to `ReviewCandidate`.
- Add OCR draft parser helpers.
- Apply drafts during `parse_suggestions`.
- Test passage prefill, circled choices, numeric choices, multiline choices,
  leading question-number cleanup, and incomplete-choice warnings.

## Acceptance criteria

- Empty passage fields initialize from raw OCR.
- Question fields initialize when choice structure is recognized.
- Warnings are stored for incomplete or ambiguous drafts.

## Validation commands

- `uv run --extra dev python -m pytest`

## Manual smoke tests

- Covered by unit tests in this phase.

## Rollback risks

- State schema changes are additive.

## Progress

- Completed.

## Decision log

- Store OCR draft metadata on `ReviewCandidate` as additive defaulted fields so
  older review-state JSON can still load.

## Outcomes / Retrospective

- Added deterministic OCR draft generation for passage body, question stem, and
  choices. Added warnings for incomplete or missing choice structure and tests
  for circled markers, numeric markers, multiline choices, forced-line-break
  joining, question-number/choice-number ambiguity, and edit preservation.
