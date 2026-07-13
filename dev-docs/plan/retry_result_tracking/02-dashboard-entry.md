# Phase 02: Add retry result entry and status UI

## Goal

- Let the user enter answers after generating a retry PDF and understand which
  questions are suppressed or retained by the next recommendation.

## Scope

- Add `/retry-results` result-entry HTML and GET/POST result JSON APIs.
- Link the new page from the PDF generation success message.
- Fetch latest status summaries into the live dashboard, display result/count/
  date, and add an `Include completed` selection override.
- Validate manifests, result payloads, choices, and all filesystem boundaries.

## Non-goals

- Editing canonical questions, tags, or original attempt reviews.
- Authentication or remote hosting; the server remains loopback-oriented.
- Embedding personal result history in `docs/tagging-dashboard.html`.

## Affected files

- `tools/serve_tagging_dashboard.py`
- `tools/build_tagging_dashboard.py`
- `docs/tagging-dashboard.html`
- `tests/test_build_tagging_dashboard.py`

## Implementation steps

1. Add secure manifest/result routing and response helpers.
2. Render a result form from manifest-selected questions without exposing
   correct answers before submission.
3. Submit all rows, allowing blank choices as explicit skipped outcomes.
4. Return graded results and show correct/incorrect/skipped feedback.
5. Merge `/api/retry-statuses` into live records and update selection controls.
6. Regenerate the static HTML while keeping personal data server-fetched only.

## Acceptance criteria

- The result page never embeds the answer key in its initial HTML or JSON.
- POST grading ignores client claims and uses manifest `correct_choice` values.
- A correct latest result is not recommended unless Include completed is on.
- Incorrect and skipped results remain selectable, with incorrect first.
- Traversal attempts outside `output/` or `data/retry_attempts/` are rejected.

## Validation commands

- python -m pytest -q

## Manual smoke tests

- Generate a one-question PDF in the live server flow, open result entry,
  submit a correct answer, refresh the dashboard, and verify default exclusion
  plus Include completed restoration.

## Rollback risks

- Static snapshots cannot submit without the live server; controls must explain
  this through normal API error handling rather than embedding personal data.

## Progress

- Not started.

## Decision log

- No decisions recorded yet.

## Outcomes / Retrospective

- Not completed yet.
