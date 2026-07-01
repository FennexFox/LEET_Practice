# Phase 02: Optional local Korean cleanup adapters

## Goal

- Add dependency-gated local cleanup helpers for spacing and morphology warnings.

## Scope

- Runtime-gated PyKoSpacing/KorSpacing spacing adapter.
- Runtime-gated Kiwi/kiwipiepy morphology warning adapter.
- Metadata recording for applied, unavailable, and failed cleanup steps.

## Non-goals

- No mandatory ML dependencies.
- No silent legal/exam wording rewrites beyond draft-only spacing suggestions.

## Affected files

- `src/leet_practice/verification.py`
- `tests/test_ocr_prefill.py`
- `pyproject.toml`
- `dev-docs/plan/issue_2/02-local-cleanup.md`

## Implementation steps

- Add optional dependency extra for local cleanup packages where practical.
- Implement adapters with graceful missing-backend behavior.
- Test fake installed backends and missing backends.

## Acceptance criteria

- Basic parser works without optional packages.
- Fake spacing backend can modify draft text and record correction metadata.
- Fake Kiwi backend can add morphology warnings without modifying text.

## Validation commands

- `uv run --extra dev python -m pytest`

## Manual smoke tests

- Covered by unit tests in this phase.

## Rollback risks

- Optional dependencies should not affect default install.

## Progress

- Completed.

## Decision log

- Keep PyKoSpacing/KorSpacing runtime-detected rather than mandatory
  dependencies. Add `kiwipiepy` under the optional `local-nlp` extra.

## Outcomes / Retrospective

- Added dependency-gated spacing cleanup and Kiwi morphology warnings. Tests use
  fake modules and missing-backend monkeypatches so default validation remains
  lightweight.
