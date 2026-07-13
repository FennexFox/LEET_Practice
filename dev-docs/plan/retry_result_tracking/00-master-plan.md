# Track retry outcomes and suppress completed questions

## Issue Target And Scope Summary

- Issue target: retry-result-tracking
- Title: Track retry outcomes and suppress completed questions
- Source plan: None
- Scope: Persist answers for generated retry-PDF sessions, grade them against
  the immutable manifest, show the latest retry state in the live dashboard,
  and exclude latest-correct questions from later recommendations by default.

## Strategy

- Keep PDF manifests immutable and add a stable `session_id` to every bundle.
- Store editable-per-session, append-across-session result files under
  `data/retry_attempts/`, keyed by `session_id` and `review_file`.
- Derive a latest-status index from all saved sessions. Latest incorrect
  questions are prioritized, skipped/unanswered questions remain eligible,
  and latest-correct questions are excluded unless `include_completed` is set.
- Add a server-rendered result-entry page plus validated JSON APIs. The live
  dashboard consumes status summaries without embedding personal results in
  the generated static HTML snapshot.

## Phase Order

1. [Persist retry outcomes and apply selection policy](01-storage-selection.md)
2. [Add retry result entry and status UI](02-dashboard-entry.md)
3. [Document workflow and complete validation](03-documentation-verification.md)

## Phase Dependencies

- Phase 1 has no phase dependency beyond resolved issue context.
- Phase 2 depends on completion and validation of phase 1.
- Phase 3 depends on completion and validation of phase 2.

## Source Of Truth Decisions

- `00-master-plan.md` is the phased implementation plan source of truth.
- Phase files in this directory define phase-local scope and validation.
- Earlier monolithic plans are input material only unless explicitly retained.
- PDF manifests are immutable generation provenance; result files are the
  source of truth for retry outcomes.
- `review_file` remains the stable cross-file question key.
- A session result may be corrected by resubmitting that session, while later
  sessions remain separate history entries.

## Global Validation Expectations

- python -m pytest -q

## Known Risks And Assumptions

- Existing manifests have no `session_id`; reading them derives the ID from
  the manifest filename for backward compatibility.
- A blank answer is stored as `skipped`; it makes the question eligible rather
  than silently preserving a previously correct state.
- Result files contain personal study data and must remain Git-ignored.
- Server endpoints must only read manifests under `output/` and retry results
  under `data/retry_attempts/`.
