# Phase 03: Delete retry session bundles safely

## Goal

- Add a destructive endpoint that safely removes one mistakenly generated
  retry session and its associated local files.

## Scope

- Require an exact full session ID and matching confirmation value.
- Resolve the manifest through the validated retry-session index.
- Delete the manifest, same-stem PDF when present, and saved retry result when
  present, while holding the retry-session write lock.
- Stage every existing file under a same-directory temporary name and restore
  staged files if preparation fails.
- Return non-sensitive artifact labels and clear HTTP errors.

## Non-goals

- Deleting by a 10-character short code.
- Bulk deletion, trash retention, undo, or deleting original review records.
- Deleting arbitrary paths declared inside a manifest.

## Affected files

- `tools/serve_tagging_dashboard.py`
- `tests/test_build_tagging_dashboard.py`

## Implementation steps

1. Add exact-ID record resolution for destructive operations.
2. Derive the companion PDF from the trusted manifest filename and the result
   path from the validated result API.
3. Add staged bundle deletion with rollback on preparation failure.
4. Add `DELETE /api/retry-sessions` with a JSON body containing an exact
   `session_id` and matching `confirm_session_id`.
5. Test complete, missing-companion, invalid, ambiguous, and rollback cases.

## Acceptance criteria

- A valid request removes the manifest, paired PDF, and result file.
- Missing optional PDF/result files do not prevent deleting the session.
- Short codes, mismatched confirmation, unsafe IDs, missing sessions, and
  duplicate full IDs are rejected without deleting files.
- A staging failure restores every file moved earlier in that operation.
- Responses do not expose local filesystem paths or manifest contents.

## Validation commands

- python -m pytest -q

## Manual smoke tests

- Create an isolated synthetic session, delete it over HTTP, confirm all three
  files are gone and the recent-session API no longer returns it.

## Rollback risks

- An open PDF can prevent Windows rename operations; preparation rollback must
  leave the original session discoverable rather than partially deleting it.

## Progress

- Added a JSON-validated `DELETE /api/retry-sessions` endpoint requiring the
  exact full session ID twice and rejecting unknown fields or short codes.
- Added trusted-root derivation for same-stem PDFs and deterministic result
  paths without following manifest-supplied deletion paths.
- Added same-directory staging, reverse rollback on preparation failure,
  Windows file-lock conflict reporting, and cleanup-pending labels.
- Serialized result validation/saving and bundle deletion under one reentrant
  lifecycle lock.
- Added full bundle, missing companion, unsafe path, duplicate ID, repeated
  delete, rollback, and cleanup-pending regression coverage.

## Decision log

- Delete the complete generated session because the motivating case is an
  incorrect generation, while answer-entry mistakes remain correctable by
  resubmitting the existing session.
- Use a JSON DELETE request rather than query parameters so the destructive
  contract rejects unknown input and remains non-simple cross-origin traffic.
- Ignore the manifest's raw `pdf_path`; only the validated manifest's same-stem
  sibling can be proven to belong to the session.

## Outcomes / Retrospective

- Focused deletion validation: 5 tests passed.
- Full regression validation: 173 tests passed.
- Isolated HTTP smoke: session count changed from 1 to 0, manifest/PDF/result
  were all absent, and the deleted result-entry URL returned HTTP 404.
- `git diff --check` passed; only repository line-ending warnings remain.
