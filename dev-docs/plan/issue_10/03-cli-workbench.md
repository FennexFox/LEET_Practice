# Phase 03: CLI and browser workbench

## Goal

- Add a separate local browser workbench command for self-review and feedback resolution.

## Scope

- `leet-practice attempt-review serve <attempt_id>` command.
- Optional helpers for attempt creation/grading, feedback export, and feedback import if needed to make the workflow usable.
- Local HTTP API and HTML workbench for wrong-question free-form self-review.
- Loopback host guard matching the verification workbench.

## Non-goals

- No changes to `leet-practice verify`.
- No production web app or authentication.
- No direct model/API calls.

## Affected files

- `src/leet_practice/cli.py`
- `src/leet_practice/attempt_review.py`
- `tests/test_attempt_review_workbench.py`
- `tests/test_cli.py`

## Implementation steps

- Add Typer command group.
- Add server factory and request handler.
- Add minimal HTML with queue, question/choice display, self-review fields, assistant feedback display, and resolution controls.
- Add CLI/workbench tests.

## Acceptance criteria

- The new command serves a separate browser UI.
- User can enter free-form self-review for wrong questions.
- User can accept, edit, or reject assistant feedback.
- Assistant feedback remains separate from user input.

## Validation commands

- python -m pytest

## Manual smoke tests

- Invoke CLI help for the new command.
- Start the server on port 0 in tests and exercise API endpoints.

## Rollback risks

- Moderate. CLI registration must preserve existing commands and hidden aliases.

## Progress

- Added `leet-practice attempt-review` Typer group.
- Added `create`, `grade`, `feedback-export`, `feedback-import`, and `serve` commands.
- Added local HTTP workbench with `GET /`, `GET /api/state`, `POST /api/reviews/<question_no>/self-review`, and `POST /api/reviews/<question_no>/resolution`.
- Added CLI and workbench tests.

## Decision log

- Default port is `8766` to avoid colliding with OCR verification's `8765`.
- Non-loopback hosts are rejected unless `--unsafe-allow-remote` is explicitly set.
- The workbench uses the existing standard-library HTTP pattern rather than introducing a web framework.

## Outcomes / Retrospective

- Completed. CLI help smoke checks passed for `attempt-review` and `attempt-review serve`.
