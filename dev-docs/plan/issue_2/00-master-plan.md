# Add OCR-derived prefill and local Korean cleanup suggestions

## Issue Target And Scope Summary

- Issue target: #2
- Title: Add OCR-derived prefill and local Korean cleanup suggestions for verification workbench
- Scope: Add OCR-derived draft fields, deterministic question/choice parsing,
  dependency-gated local Korean spacing cleanup, dependency-gated Kiwi
  morphology warnings, and UI controls to apply drafts explicitly.

## Strategy

- Keep `raw_ocr_text` immutable as source evidence.
- Add draft metadata directly to `ReviewCandidate` so state files are
  self-contained.
- Prefill empty editable fields only when a review state is first initialized.
- Make optional local NLP backends runtime-gated with `importlib`; tests use
  monkeypatched fake modules rather than installing heavyweight packages.
- Expose draft warnings and an explicit `Apply OCR draft` action in the local
  workbench.

## Phase Order

1. [Deterministic OCR draft parser](01-draft-parser.md)
2. [Optional local Korean cleanup adapters](02-local-cleanup.md)
3. [Review UX integration](03-ux-integration.md)
4. [Validation and documentation](04-verification.md)

## Phase Dependencies

- Phase 1 has no dependency beyond current issue #2 branch state.
- Phase 2 depends on draft metadata from phase 1.
- Phase 3 depends on parser and adapter APIs from phases 1-2.
- Phase 4 validates the completed feature and updates docs.

## Source Of Truth Decisions

- This plan directory is the implementation source of truth for issue #2.
- Issue #2 body defines acceptance criteria.
- `docs/verification-workbench.md` remains the user-facing workflow reference.

## Global Validation Expectations

- `uv run --extra dev python -m pytest`
- `uv run leet-practice review-crops --help`

## Known Risks And Assumptions

- PyKoSpacing/KorSpacing and kiwipiepy can be heavy or unavailable on Windows,
  so they must never be required for the basic workbench.
- OCR cleanup is a draft suggestion only; canonical promotion still depends on
  human acceptance.
- The current branch already includes #1 workbench functionality plus local UI
  improvements; preserve those changes.
