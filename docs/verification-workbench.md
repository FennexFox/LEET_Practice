# Verification workbench

The OCR and crop-suggestion pipeline produces candidate artifacts, not canonical
question data. The next workflow should let a human verify those candidates
quickly while preserving source-image provenance.

## Goal

The first implementation is a local browser-based review workbench that turns
`artifacts/question_crop_suggestions/<run_id>/suggestions.json` into verified
passage and question records.

The workbench should optimize for fast visual checking:

- confirm that each crop preview matches the intended passage or question
- compare raw OCR text against the source image
- edit verified text before it becomes learning data
- preserve page, column, image, and crop-coordinate provenance
- keep unverified OCR candidates separate from canonical data

## Command shape

Start a review session:

```powershell
leet-practice verify leet-2026-verbal-even
```

Use `--init-only` to create or refresh review state without starting the
server. Use `--no-open` to start the server without opening a browser.
By default, the command uses the latest matching
`artifacts/question_crop_suggestions/<exam_id>*/suggestions.json`. Pass
`--suggestions` only when you need a specific run.

Use optional local cleanup only when you want OCR draft suggestions to run
through local helpers during initialization:

```powershell
leet-practice verify leet-2026-verbal-even `
  --enable-spacing-cleanup `
  --enable-morphology-checks `
  --local-nlp-workers 4
```

Spacing cleanup tries local `pykospacing` first, then `korspacing`, and then
`kiwipiepy` when those packages are installed. Morphology checks also use
`kiwipiepy` when installed. Missing optional packages are recorded as draft
warnings instead of blocking review.

The local cleanup backends are initialized once while building or refreshing a
review state and then reused for all candidates in that run. `--local-nlp-workers`
applies only to optional Kiwi morphology checks; it does not change spacing
cleanup behavior. When Kiwi batch analysis is unavailable, morphology checks
fall back to the existing per-candidate path.

The command starts a local server and opens a browser-based review UI by
default.
This keeps image inspection and text editing practical without committing to a
polished production web app too early.

## Interface layout

### Left queue

Show the candidate review queue:

- passage candidates, such as `set_01_03_passage_candidate`
- question candidates, such as `q01_candidate`
- grouping by detected set, such as `[1~3] passage`, `1`, `2`, `3`
- status filters: `unreviewed`, `accepted`, `needs_fix`, `rejected`

### Center source view

Show the source evidence:

- stitched preview image
- zoom controls
- page and column provenance
- optional source-page crop coordinates for debugging

The first decision should be whether the crop itself is usable. Text editing is
secondary if the crop is wrong.

### Right text editor

Show structured text fields:

- raw OCR text as read-only reference
- verified passage body for passage candidates
- question stem and choices 1-5 for question candidates
- question number
- linked passage ID or set range
- answer key confirmation when available

Verified text is the only text that should later move into canonical data.
The editor should hide passage-only fields while reviewing questions and hide
question-only fields while reviewing passages. Raw OCR should be copyable from
the browser UI for quick manual cleanup.

Editable fields are prefilled from OCR drafts on first initialization:

- passage body starts from the full raw OCR text
- question stem and choices are split by common markers such as `①` through `⑤`,
  `1)`, `1.`, and `(1)`
- forced OCR line breaks are joined in draft fields while Raw OCR keeps the
  original line breaks
- obvious missing spaces after punctuation are normalized in draft fields, while
  numeric values such as `1,000` and `3.14` are preserved
- numeric choice markers are accepted in sequence from 1, reducing cases where a
  question number such as `5.` is mistaken for choice 5
- draft warnings and correction steps are shown in the workbench
- `Apply OCR draft` explicitly replaces the current editable fields with the OCR
  draft again

Normal reloads do not overwrite user edits. Reapplying a draft is always an
explicit reviewer action.

### Actions

Support these actions:

- `Accept`: crop and verified text are usable
- `Needs recrop`: candidate is close but needs a manual or adjusted crop
- `Reject`: candidate should not become data
- `Save`: persist current edits
- `Apply OCR draft`: replace editable fields with the latest OCR draft
- `Next`: move to the next unresolved candidate

Autosave is preferred so the reviewer can move quickly without losing edits.

## Review-state storage

Do not write directly to `data/canonical/` from the review UI. Store review
state and verified drafts under a separate local verification area first:

```text
data/verification/leet-2026-verbal-even/
  crop-review-state.json
  verified_passages.jsonl
  verified_questions.jsonl
```

Suggested responsibilities:

- `crop-review-state.json`: UI state, candidate statuses, notes, and provenance
- `verified_passages.jsonl`: accepted passage drafts
- `verified_questions.jsonl`: accepted question drafts

These files may contain official text and should remain local by default.

## Promotion step

Canonical data should be updated only by an explicit promotion command:

```powershell
leet-practice promote leet-2026-verbal-even
```

The promotion command should validate:

- required exam metadata exists
- question numbers are unique
- accepted questions have valid answer choices
- passage links point to accepted or existing passages
- source provenance exists for every promoted record

Only after validation should records be written to:

```text
data/canonical/leet-2026-verbal-even/
  passages.jsonl
  questions.jsonl
```

## Boundary rule

The important boundary is:

```text
raw OCR -> OCR draft fields -> local cleanup suggestions -> human verification -> canonical question bank
```

The review UI is a fast decision and correction tool. `data/canonical/` is for
verified records only.
