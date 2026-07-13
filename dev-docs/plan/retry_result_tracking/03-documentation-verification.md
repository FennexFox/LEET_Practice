# Phase 03: Document workflow and complete validation

## Goal

- Finish user-facing documentation and validate the entire workflow, including
  PDF layout after adding session identification.

## Scope

- Document result entry, exclusion policy, include-completed override, storage,
  and privacy behavior.
- Run focused and full automated tests, JS syntax checks, CLI smoke tests, and
  dashboard snapshot regeneration.
- Generate a real sample PDF/result session, render representative pages, and
  visually inspect session text, headers, footers, and appendix separation.

## Non-goals

- New scheduling/mastery algorithms beyond latest-result behavior.
- Shipping generated PDFs or personal retry-result files.

## Affected files

- `README.md`
- `docs/data-layout.md`
- Phase plan outcome sections

## Implementation steps

1. Update workflow and data-layout documentation.
2. Regenerate dashboard HTML and verify no personal retry data is embedded.
3. Run all automated and manual validation listed in this phase.
4. Record final outcomes, commit IDs, and remaining limitations.

## Acceptance criteria

- Documentation exactly matches the implemented policy and API behavior.
- Full test suite and `git diff --check` pass.
- Rendered PDF has no clipping, overlap, broken Korean glyphs, or answer leakage.
- No generated PDF, graph output, or personal result file is committed.

## Validation commands

- python -m pytest -q

## Manual smoke tests

- Run the live dashboard, generate a PDF, submit mixed outcomes, generate the
  next recommendation, and verify correct exclusion/incorrect retention.

## Rollback risks

- PDF rendering depends on a Korean system font; use the established explicit
  font override if automatic discovery is unavailable.

## Progress

- Not started.

## Decision log

- No decisions recorded yet.

## Outcomes / Retrospective

- Not completed yet.
