# Order retry recommendations by review age

## Issue Target And Scope Summary

- Issue target: user-request-2026-07-13
- Scope: keep retry-history tiers and primary-tag balancing intact while preferring older user-entered self-reviews and ordering each balanced tier result from oldest input to newest input.
- Expected user outcome: recently entered wrong-answer reviews appear later in the recommended selection, reducing accidental recall-based retries.

## Strategy

- Treat `user_self_review.updated_at` on each review JSON as the review input time because it changes when the user saves review content, unlike top-level timestamps that also change for regrading, feedback, and resolution activity.
- Copy that value into generated tagging records as `review_input_at` so the static dashboard can sort without filesystem access.
- Add the timestamp to the backend recommendation sort key, with deterministic fallback behavior for legacy records that do not have the field.
- Apply the same comparison in dashboard JavaScript, chronologically order each tier's balanced result, and regenerate tracked tagging/dashboard artifacts.
- Preserve explicit-selection order, retry-history tier priority, tag balancing, confidence ordering after review time, and completed/holdout policies.

## Phase Order

1. [Confirm recommendation paths and timestamp contract](01-discovery.md)
2. [Implement backend and dashboard ordering](02-implementation.md)
3. [Run regression and artifact verification](03-verification.md)

## Phase Dependencies

- Phase 1 has no phase dependency beyond the user request and repository source.
- Phase 2 depends on the timestamp and fallback decisions recorded in phase 1.
- Phase 3 depends on all production, test, and generated-artifact changes from phase 2.

## Source Of Truth Decisions

- `00-master-plan.md` is the implementation-plan source of truth.
- `AttemptReviewRecord.user_self_review.updated_at` in each review JSON is the source of truth for the latest review input time.
- `review_input_at` in `provisional_tags.jsonl` is a denormalized value for recommendation consumers.
- The Python selector defines backend behavior; dashboard JavaScript must mirror it for preselection.

## Global Validation Expectations

- `python -m pytest tests/test_retry_pdf.py tests/test_build_tagging_dashboard.py`
- `python -m pytest`
- Regenerated `data/tagging/provisional_tags.jsonl` and `docs/tagging-dashboard.html` contain `review_input_at` and pass repository data/dashboard tests.

## Known Risks And Assumptions

- Legacy or hand-authored tagging rows may lack or contain malformed timestamps; they must remain selectable with deterministic fallback ordering.
- The sort only changes order within a retry-history tier and tag queue; it must not let a newer incorrect retry fall behind a never-retried item.
- Regenerating artifacts may be large, so diffs must be checked for expected timestamp/order-only changes.
