# Phase 01: Discovery and boundaries

## Goal

- Confirm issue requirements, user decisions, repository conventions, and dirty worktree state before implementation.

## Scope

- Read remote issue #10 and local docs/models/workbench patterns.
- Record clarified v1 source-of-truth decisions.
- Identify unrelated local changes and avoid touching them.

## Non-goals

- No code implementation in this phase.
- No changes to OCR verification behavior.

## Affected files

- `dev-docs/plan/issue_10/00-master-plan.md`
- `dev-docs/plan/issue_10/01-discovery.md`

## Implementation steps

- Fetch issue #10 body and comments.
- Inspect README, data layout docs, verification workbench docs, models, CLI, and relevant tests.
- Document resolved decisions in the master plan.

## Acceptance criteria

- The implementation scope is explicit.
- The data layout and command boundary decisions are written down.
- Dirty worktree files are known and left untouched.

## Validation commands

- python -m pytest

## Manual smoke tests

- Not applicable for discovery.

## Rollback risks

- Low. Plan-only changes can be reverted independently.

## Progress

- Completed issue read and local source review.
- Noted pre-existing local changes: deleted `data/verification/.gitkeep`, untracked `tools/preprocess_verification_state.py`.

## Decision log

- Keep v1 reviews under `data/reviews/<attempt_id>/`.
- Use `data/attempts/<attempt_id>.json` for attempt-level answers.
- Prefer canonical `answer_key.json`; fallback to `questions.jsonl`; error on disagreement.
- Deprecate the legacy fixed-taxonomy `Review` model for this workflow.
- Metadata fields are enough for v1 audit separation; append-only history is deferred.
- Use a separate `attempt-review` browser command, not the OCR `verify` workbench.

## Outcomes / Retrospective

- Discovery completed with enough clarity to implement without further user questions.
