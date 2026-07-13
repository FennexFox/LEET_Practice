# Phase 01: Confirm recommendation paths and timestamp contract

## Goal

- Identify every recommendation-ordering consumer and select the correct persisted review timestamp.

## Scope

- Inspect retry PDF selection, dashboard recommendation JavaScript, provisional-tag generation, review models, tests, and documentation.
- Record current precedence rules that must remain unchanged.

## Non-goals

- No production behavior changes in this phase.
- No redesign of tag balancing or retry-history tiers.

## Affected files

- `src/leet_practice/retry_pdf.py`
- `tools/build_tagging_dashboard.py`
- `tools/generate_provisional_tags.py`
- `src/leet_practice/models.py`
- `tests/test_retry_pdf.py`
- `tests/test_build_tagging_dashboard.py`

## Implementation steps

1. Trace browser preselection and backend PDF selection.
2. Verify review JSON timestamp semantics.
3. Define behavior for equal, missing, and malformed timestamps.
4. Identify generated artifacts and validation commands.

## Acceptance criteria

- Both ordering implementations are identified.
- `AttemptReviewRecord.user_self_review.updated_at` is confirmed as input time.
- Existing precedence and fallback rules are documented.

## Validation commands

- `python -m pytest tests/test_retry_pdf.py tests/test_build_tagging_dashboard.py`

## Manual smoke tests

- Inspect one tracked review JSON and its generated tagging row to confirm the timestamp can be propagated without private review text changes.

## Rollback risks

- None; this phase is documentation and investigation only.

## Progress

- Completed source and graph review.
- Baseline focused suite passed: 36 tests.

## Decision log

- Recommendation ordering exists in `retry_pdf._record_sort_key()` and dashboard `compareRetryRecords()`.
- Use `user_self_review.updated_at`; top-level `updated_at` also changes for regrading, feedback imports, and resolution, while nested `created_at` may predate actual user input.
- Sort valid timestamps ascending; missing or malformed timestamps sort after valid timestamps and then use the existing confidence/exam/question/file key.
- Keep retry-history tiers and tag-balanced membership; sort each tier's selected result chronologically so recent inputs appear later without redesigning eligibility.
- Explicitly selected review files retain caller order.

## Outcomes / Retrospective

- The smallest consistent change spans tagging generation, backend selection, dashboard JavaScript, focused tests, and regenerated artifacts/documentation.
- Baseline behavior is green before implementation, so later failures can be attributed to the scoped change.
