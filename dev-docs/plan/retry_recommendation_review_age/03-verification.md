# Phase 03: Run regression and artifact verification

## Goal

- Regenerate tracked data/dashboard outputs and prove the recommendation change is complete and regression-safe.

## Scope

- Regenerate provisional tagging data and static dashboard.
- Run focused and full tests.
- Review diffs and confirm only intended files are committed.

## Non-goals

- New recommendation features beyond chronological review-age ordering.
- Changes to private review content.

## Affected files

- `data/tagging/provisional_tags.jsonl`
- `docs/tagging-dashboard.html`
- Phase plan documents

## Implementation steps

1. Run the repository tagging generator and dashboard builder.
2. Confirm every generated active row has `review_input_at` from its source `user_self_review.updated_at`.
3. Run focused and full test suites.
4. Inspect generated diffs for unexpected content changes.
5. Record validation results and residual risks.

## Acceptance criteria

- Tracked tagging/dashboard artifacts reflect the new timestamp field and comparator.
- Focused and full test suites pass.
- Worktree contains no unrelated modifications.

## Validation commands

- `python tools/generate_provisional_tags.py`
- `python tools/build_tagging_dashboard.py`
- `python -m pytest tests/test_retry_pdf.py tests/test_build_tagging_dashboard.py`
- `python -m pytest`

## Manual smoke tests

- Inspect the generated dashboard payload/comparator and a representative pair of old/new reviews.

## Rollback risks

- Generated artifact churn may hide unrelated data changes; diff statistics and sampled content must be reviewed before commit.

## Progress

- Regenerated 95 provisional tagging rows and the static dashboard.
- Verified all 95 `review_input_at` values exactly match source `user_self_review.updated_at` values.
- Verified removing the new timestamp field makes every generated tagging row identical to the pre-change artifact.
- Verified a 20-question recommendation is chronologically ascending within its tier and excludes the corpus's newest review inputs at that limit.
- Generated dashboard JavaScript passed `node --check`.
- Focused suite passed: 38 tests; full suite passed: 176 tests.

## Decision log

- Added a tracked-data assertion requiring every generated tagging record to carry a non-empty `review_input_at`.
- Kept generated review/tag content unchanged apart from the new timestamp field and dashboard comparator code.

## Outcomes / Retrospective

- The newest selected input in the 20-question smoke test was 2026-07-07, while the corpus newest was 2026-07-13, confirming recent reviews no longer jump ahead of older same-tier/tag candidates.
- No residual test failures or artifact mismatches remain.
