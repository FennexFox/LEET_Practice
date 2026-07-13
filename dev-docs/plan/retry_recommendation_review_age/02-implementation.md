# Phase 02: Implement backend and dashboard ordering

## Goal

- Make recommended retry selections place older reviews before recently entered reviews without changing higher-level eligibility or balancing rules.

## Scope

- Propagate `user_self_review.updated_at` into tagging rows as `review_input_at`.
- Update Python and JavaScript comparison keys.
- Add focused regression tests for ascending review age and legacy fallback.
- Update user-facing retry recommendation documentation.

## Non-goals

- Explicit-selection order changes.
- Retry result scoring, session storage, or PDF layout changes.
- Database or schema migration work.

## Affected files

- `tools/generate_provisional_tags.py`
- `src/leet_practice/retry_pdf.py`
- `tools/build_tagging_dashboard.py`
- `tests/test_retry_pdf.py`
- `tests/test_build_tagging_dashboard.py`
- `README.md`

## Implementation steps

1. Add `review_input_at` to generated records.
2. Parse valid timestamps into an ascending Python sort key with a legacy fallback bucket.
3. Mirror the timestamp-first key in JavaScript.
4. Chronologically order the balanced output inside each retry-history tier.
5. Add tests proving newer reviews are later inside the same tier/tag and explicit selection is unchanged.
6. Describe the new tie-breaking order in the README.

## Acceptance criteria

- Oldest valid `review_input_at` is selected first within a history tier and primary-tag queue, and the tier's balanced result is emitted oldest-first.
- Missing/invalid timestamps do not crash recommendation generation.
- Retry tiers, tag balancing, filters, and explicit order remain intact.
- Browser and backend use equivalent ordering.

## Validation commands

- `python -m pytest tests/test_retry_pdf.py tests/test_build_tagging_dashboard.py`

## Manual smoke tests

- Generate or inspect a recommendation containing old and recent same-tag records and verify the recent record is later.

## Rollback risks

- A comparator mismatch could make browser preselection differ from direct CLI recommendations.
- Timestamp string normalization must handle timezone-aware, naive, and legacy values consistently enough for deterministic order.

## Progress

- Added `review_input_at` propagation from `user_self_review.updated_at`.
- Updated Python and browser recommendation comparators and chronological tier output.
- Added backend ordering, invalid/missing timestamp, and retry-tier regression coverage.
- Focused suite passed: 38 tests; Python source compilation passed.

## Decision log

- Retry-history tier remains the highest priority.
- Tag balancing continues to choose the membership of each tier's recommendation; review time is primary inside tag queues, then the balanced result is emitted chronologically.
- Naive ISO timestamps are interpreted as UTC in both consumers for deterministic cross-environment ordering.
- Missing and malformed timestamps sort after valid timestamps, then fall back to confidence/year/section/question/file ordering.

## Outcomes / Retrospective

- Browser preselection and direct Python/CLI recommendation now share equivalent review-age semantics.
- Explicit review-file selections bypass recommendation sorting and continue to preserve caller order.
