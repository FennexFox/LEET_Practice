# Phase 01: Persist retry outcomes and apply selection policy

## Goal

- Add durable retry-session result storage and make selection history-aware.

## Scope

- Add a focused retry-results module with schema validation, grading, atomic
  writes, latest-status aggregation, and backward-compatible manifest loading.
- Add `session_id` to generated bundles/manifests and expose
  `include_completed` through the shared generator and CLI.
- Exclude latest-correct questions by default and rank latest-incorrect
  questions before unseen/skipped questions inside each primary-tag queue.
- Ignore `data/retry_attempts/` in Git.

## Non-goals

- Dashboard HTTP routes and result-entry UI.
- Spaced-repetition scheduling or multi-correct mastery thresholds.
- Changes to the original attempt-review records.

## Affected files

- `src/leet_practice/retry_results.py`
- `src/leet_practice/retry_pdf.py`
- `src/leet_practice/cli.py`
- `.gitignore`
- Focused core and CLI tests

## Implementation steps

1. Define session, item, and latest-question status dataclasses.
2. Load and validate manifests; grade submitted choices server-side.
3. Save one JSON file per session with stable timestamps and safe identifiers.
4. Aggregate latest outcome and attempt counts by normalized `review_file`.
5. Integrate status filtering/ranking into retry selection and bundle creation.
6. Add `session_id` to the PDF subtitle, manifest, return type, and CLI output.

## Acceptance criteria

- Latest correct is excluded by default; latest incorrect is selected first.
- `include_completed=True` restores completed questions after other candidates.
- Unknown files, choices outside 1-5, manifest mismatches, and unsafe session
  IDs fail with a domain error and do not partially write results.
- Legacy manifests without `session_id` remain readable.
- Existing retry-PDF and CLI behavior remains compatible when no history exists.

## Validation commands

- python -m pytest -q

## Manual smoke tests

- Generate a small session, save correct/incorrect/skipped results, then create
  a second bundle and inspect the resulting selection order.

## Rollback risks

- A bad aggregation rule could hide questions unexpectedly. The latest-status
  index and include-completed override keep the behavior reversible.

## Progress

- Completed retry-result schema, manifest validation, server-side grading,
  atomic per-session persistence, and latest-status aggregation.
- Integrated history tiers, latest-correct suppression, incorrect priority,
  `include_completed`, session IDs, and CLI exposure.
- Added core, selection, manifest, persistence, and CLI regression tests.

## Decision log

- Result files use `data/retry_attempts/` to match the terminology promised in
  the user-facing design while remaining separate from original attempts.
- Resubmission replaces one session result so entry mistakes can be corrected;
  separate PDF sessions remain append-only history.
- Selection recomputes effective correctness against the current tagging
  answer when possible, protecting against corrected answer keys.

## Outcomes / Retrospective

- Focused validation: 39 tests passed.
- Full validation: 162 tests passed.
- `git diff --check` passed; only repository line-ending warnings remain.
