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

- Documented result entry, history-based ordering, latest-correct exclusion,
  Include completed, resubmission, and local personal-data storage.
- Regenerated the static dashboard and verified that the QA session identifier
  was not embedded in it.
- Completed automated, CLI, HTTP, and rendered-PDF validation without leaving
  generated personal/output data in the repository.

## Decision log

- Documentation states the exact implemented tier order: latest incorrect,
  latest skipped, never retried, then latest correct only when Include
  completed is enabled.
- Objective difficulty is deliberately absent from retry-history ranking; tag
  balancing remains the secondary distribution mechanism.
- PDF visual QA used the explicit Windows Malgun Gothic font and PyMuPDF
  rendering because a Poppler command was unavailable in the environment.

## Outcomes / Retrospective

- Full validation: 165 tests passed.
- Both inline JavaScript bundles passed `node --check`; the CLI help smoke test
  exposed `--include-completed` with the documented behavior.
- A three-question real-data workbook produced a schema-v2 manifest with the
  same session ID shown on page 1. All four pages were rendered and inspected;
  Korean glyphs, content flow, headers, footers, and the answer-analysis
  appendix had no clipping or overlap.
- The static dashboard snapshot was regenerated from 95 records (90 active, 5
  holdouts), and the QA session ID was absent from the generated HTML.
- Phase 2's live HTTP smoke covered generation, result-page loading, result
  submission, and status refresh. In-app browser click testing remained
  unavailable because the runtime exposed no browser binding.
