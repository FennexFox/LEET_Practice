# Add self-review workbench and file-based assistant feedback handoff

## Issue Target And Scope Summary

- Issue target: #10
- Title: Add self-review workbench and file-based assistant feedback handoff
- Source plan: None
- Scope: Add a v1 attempt-review workflow that records attempt answers, grades them against canonical answers, lets the user enter free-form self-review for wrong questions, exports a file-based assistant-feedback bundle, imports assistant feedback separately, and lets the user resolve that feedback.

## Strategy

- Keep OCR verification and attempt review separate. Add an `attempt_review` implementation module with Pydantic models, JSON storage helpers, grading, HTTP workbench handlers, and feedback export/import helpers.
- Store attempt-level answers in `data/attempts/<attempt_id>.json`.
- Store per-question reviews in `data/reviews/<attempt_id>/qXXX.review.json`.
- Nest `grading`, `user_self_review`, `assistant_feedback`, and `user_resolution` in each review JSON file.
- Prefer `data/canonical/<exam_id>/answer_key.json` for grading. Fall back to `questions.jsonl` when no answer key exists, and error if both sources exist but disagree.
- Add a separate CLI command group: `leet-practice attempt-review ...`, with `serve <attempt_id>` as the browser entrypoint.
- Do not require fixed user-input taxonomy choices. Assistant feedback may include `provisional_error_tags`, but they remain explicitly provisional until user resolution.

## Phase Order

1. [Discovery and boundaries](01-discovery.md)
2. [Attempt review models and storage](02-models-storage.md)
3. [CLI and browser workbench](03-cli-workbench.md)
4. [Tests docs and validation](04-verification.md)

## Phase Dependencies

- Phase 1 has no phase dependency beyond resolved issue context.
- Phase 2 depends on completion and validation of phase 1.
- Phase 3 depends on completion and validation of phase 2.
- Phase 4 depends on completion and validation of phase 3.

## Source Of Truth Decisions

- `00-master-plan.md` is the phased implementation plan source of truth.
- Phase files in this directory define phase-local scope and validation.
- Earlier monolithic plans are input material only unless explicitly retained.
- User clarification in the July 6, 2026 thread resolves issue-level ambiguities about data layout, answer-key precedence, taxonomy, immutability, and command separation.

## Global Validation Expectations

- python -m pytest

## Known Risks And Assumptions

- The canonical answer-key schema may vary in local data. V1 should support straightforward mappings and fail clearly for unsupported shapes.
- Existing local personal data is ignored by Git. Tests should use `tmp_path` fixtures rather than relying on real local data.
- The browser UI is intentionally local and unauthenticated; it must retain loopback-host safeguards.
- The existing legacy `Review` model remains for backwards compatibility but should not be used by the new workflow.
