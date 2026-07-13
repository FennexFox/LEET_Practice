# Reopen retry sessions by ID

## Issue Target And Scope Summary

- Issue target: retry-session-reopen
- Title: Reopen retry sessions by ID
- Source plan: None
- Scope: Make generated retry-PDF sessions discoverable after generation so a
  learner can enter results later using the session ID printed in the PDF or
  its unique final 10-character code, without retaining the generation tab.

## Strategy

- Treat manifest JSON files under `output/pdf/retry-pdfs/` as the durable
  session index and never search outside that trusted root.
- Resolve exact session IDs or unique 10-character suffixes, rejecting missing
  and ambiguous matches explicitly.
- Expose sanitized recent-session summaries from the local dashboard server
  and add dashboard controls for lookup and recent-history reopening.
- Keep the existing manifest-path URL compatible while making session-based
  URLs the default for newly generated PDFs.

## Phase Order

1. [Discover and resolve retry sessions](01-session-index-api.md)
2. [Add reopen controls and verify the workflow](02-dashboard-reopen-ui.md)

## Phase Dependencies

- Phase 1 has no phase dependency beyond resolved issue context.
- Phase 2 depends on completion and validation of phase 1.

## Source Of Truth Decisions

- `00-master-plan.md` is the phased implementation plan source of truth.
- Phase files in this directory define phase-local scope and validation.
- Earlier monolithic plans are input material only unless explicitly retained.

## Global Validation Expectations

- python -m pytest -q

## Completion Status

- Phase 1 completed with validated manifest discovery, ID resolution, and the
  recent-session API.
- Phase 2 not started.

## Known Risks And Assumptions

- The manifest directory can contain malformed or unrelated JSON; discovery
  must skip invalid entries without exposing answer keys through the API.
- Session suffixes are UUID-derived and normally unique, but ambiguity must
  fail rather than selecting an arbitrary manifest.
- Output manifests are locally generated and Git-ignored; reopening works
  across server restarts while the corresponding manifest remains on disk.
