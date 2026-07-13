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

- Not started.

## Decision log

- No verification decisions recorded yet.

## Outcomes / Retrospective

- Not completed yet.
