# Implement local verification workbench for OCR crop suggestions

## Issue Target And Scope Summary

- Issue target: #1
- Title: Implement local verification workbench for OCR crop suggestions
- Source plan: `docs/verification-workbench.md`
- Scope: Implement a local-first verification path from
  `artifacts/question_crop_suggestions/<run_id>/suggestions.json` into
  `data/verification/<exam_id>/`, expose a lightweight browser UI for review,
  and add explicit promotion into `data/canonical/<exam_id>/` after validation.

## Strategy

- Add storage-layer functions and Pydantic models for review candidates, review
  state, verified passage drafts, verified question drafts, and source
  provenance.
- Keep the first browser workbench dependency-light by serving static HTML and
  JSON endpoints from the Python standard library. This avoids committing to a
  production web framework before the workflow stabilizes.
- Make promotion a separate CLI command so canonical files are never updated by
  OCR parsing or autosave alone.
- Cover parser/storage/promotion behavior with pytest tests using small synthetic
  `suggestions.json` fixtures.

## Phase Order

1. [Verification state models and storage](01-storage.md)
2. [Local browser review workbench](02-workbench.md)
3. [Canonical promotion validation](03-promotion.md)

## Phase Dependencies

- Phase 1 has no phase dependency beyond resolved issue context.
- Phase 2 depends on completion and validation of phase 1.
- Phase 3 depends on completion and validation of phase 2.

## Source Of Truth Decisions

- `00-master-plan.md` is the phased implementation plan source of truth.
- Phase files in this directory define phase-local scope and validation.
- `docs/verification-workbench.md` is the product/workflow design reference.

## Global Validation Expectations

- `uv run --extra dev python -m pytest`
- If uv is unavailable, `python -m pytest`

## Known Risks And Assumptions

- The current repository has no implemented persistence layer beyond Pydantic
  concept models, so JSON/JSONL files are the correct first storage target.
- `suggestions.json` shape is produced by a local tool and may evolve; parsing
  should preserve unknown candidate fields in provenance rather than requiring a
  brittle exact schema.
- Browser UI smoke tests can be limited to endpoint-level tests in this phase;
  visual browser automation is not required for issue #1.
- Local data under `data/verification/` and `data/canonical/` may contain
  official text and remains ignored by Git.
