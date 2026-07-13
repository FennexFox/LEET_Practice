# Reopen and manage retry sessions

## Issue Target And Scope Summary

- Issue target: retry-session-reopen
- Title: Reopen and manage retry sessions
- Source plan: None
- Scope: Make generated retry-PDF sessions discoverable after generation so a
  learner can enter results later using the session ID printed in the PDF or
  its unique final 10-character code, without retaining the generation tab,
  and safely remove a session created by mistake.

## Strategy

- Treat manifest JSON files under `output/pdf/retry-pdfs/` as the durable
  session index and never search outside that trusted root.
- Resolve exact session IDs or unique 10-character suffixes, rejecting missing
  and ambiguous matches explicitly.
- Expose sanitized recent-session summaries from the local dashboard server
  and add dashboard controls for lookup and recent-history reopening.
- Keep the existing manifest-path URL compatible while making session-based
  URLs the default for newly generated PDFs.
- Delete only exact full-ID matches and treat the manifest, paired PDF, and
  optional saved result as one session bundle.

## Phase Order

1. [Discover and resolve retry sessions](01-session-index-api.md)
2. [Add reopen controls and verify the workflow](02-dashboard-reopen-ui.md)
3. [Delete retry session bundles safely](03-session-deletion-api.md)
4. [Add dashboard deletion controls](04-session-deletion-ui.md)

## Phase Dependencies

- Phase 1 has no phase dependency beyond resolved issue context.
- Phase 2 depends on completion and validation of phase 1.
- Phase 3 depends on the exact-ID index from phase 1.
- Phase 4 depends on the deletion endpoint from phase 3.

## Source Of Truth Decisions

- `00-master-plan.md` is the phased implementation plan source of truth.
- Phase files in this directory define phase-local scope and validation.
- Earlier monolithic plans are input material only unless explicitly retained.

## Global Validation Expectations

- python -m pytest -q

## Completion Status

- Phase 1 completed in `4967636` with validated manifest discovery, ID
  resolution, and the recent-session API.
- Phase 2 completed with delayed-entry controls, recent history, documentation,
  and restart validation.
- Phase 3 completed with exact-ID confirmed bundle deletion, staged rollback,
  lifecycle locking, and HTTP validation.
- Phase 4 not started.

## Known Risks And Assumptions

- The manifest directory can contain malformed or unrelated JSON; discovery
  must skip invalid entries without exposing answer keys through the API.
- Session suffixes are UUID-derived and normally unique, but ambiguity must
  fail rather than selecting an arbitrary manifest.
- Output manifests are locally generated and Git-ignored; reopening works
  across server restarts while the corresponding manifest remains on disk.
- Deletion is irreversible and may encounter an open PDF on Windows; staging
  every existing bundle file before unlinking avoids common partial deletes.
