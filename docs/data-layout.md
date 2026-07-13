# Data layout

This project uses a local-first data layout. The directories under `data/` are intentionally created but ignored by Git, except for `.gitkeep` placeholders.

## Exam IDs

Use stable, human-readable exam IDs:

```text
leet-2026-verbal-even
leet-2026-verbal-odd
leet-2026-reasoning-even
leet-2025-verbal-even
```

Suggested fields encoded in the ID:

```text
<exam>-<year>-<subject>-<form>
```

- `exam`: `leet`, `psat`, or another stable exam family name
- `year`: exam admission year or official test year, consistently chosen
- `subject`: `verbal`, `reasoning`, `writing`, etc.
- `form`: `odd`, `even`, `a`, `b`, or another official form marker

## Directory roles

### `data/raw_pdfs/`

Local official PDF files.

Example:

```text
data/raw_pdfs/leet-2026-verbal-even.pdf
data/raw_pdfs/leet-2026-verbal-even-answers.pdf
```

Do not commit these files unless you have a clear legal reason to do so.

### `data/rendered_pages/`

Rendered page images from PDFs.

Example:

```text
data/rendered_pages/leet-2026-verbal-even/
  page_001_300dpi.png
  page_002_300dpi.png
```

These images are treated as local evidence artifacts and are ignored by Git.

### `data/ocr/`

Raw OCR outputs, OCR JSON, and intermediate parsing drafts.

Example:

```text
data/ocr/leet-2026-verbal-even/
  page_001_left.paddleocr.txt
  page_001_left.paddleocr.json
  q01_ocr_raw.txt
```

OCR output is never treated as final truth. It must be reviewed before becoming verified text.

### `artifacts/question_crop_suggestions/`

Candidate crop-suggestion runs from `tools/suggest_question_crops.py`.

Example:

```text
artifacts/question_crop_suggestions/20260630-131213/
  page_001_300dpi.png
  page_001_left.png
  page_001_left.paddleocr.json
  p001_left_annotated.png
  set_01_03_passage_candidate/
    set_01_03_passage_candidate_preview.png
  q01_candidate/
    q01_candidate_preview.png
  suggestions.json
```

These are local evidence artifacts. Per-column `*.paddleocr.json` files are
compact OCR-row/provenance records by default, not full PaddleOCR raw payload
dumps. `suggestions.json` preserves selected set-header anchors, selected
question anchors, passage/question candidate separation, page, column,
source-image, local crop, and source-page crop provenance for every candidate
part. Per-candidate `part_*_left.png` / `part_*_right.png` inputs are deleted
after the stitched preview is created unless `--keep-crop-part-images` is used.
The candidates are not verified question text and should not be copied into
`data/canonical/` without review.

### `data/verification/`

Human verification drafts created from crop-suggestion runs.

Example:

```text
data/verification/leet-2026-verbal-even/
  crop-review-state.json
  verified_passages.jsonl
  verified_questions.jsonl
```

This directory is the staging area between OCR/crop suggestions and canonical
exam data. It may contain official text, so it is ignored by Git by default.
See [`docs/verification-workbench.md`](verification-workbench.md) for the
planned review interface.

### `data/canonical/`

Verified exam/question data. This may still contain official question text, so it is ignored by Git by default.

Example:

```text
data/canonical/leet-2026-verbal-even/
  exam.json
  answer_key.json
  passages.jsonl
  questions.jsonl
```

### `data/attempts/`

Personal attempt records.

Example:

```text
data/attempts/2026-06-30-leet-2026-verbal-even.json
```

The v1 attempt-review workflow stores selected answers here independently from
canonical question data. The attempt file is the source for what the user chose;
canonical `answer_key.json` or `questions.jsonl` remains the source for official
answers.

### `data/reviews/`

Wrong-answer reviews and evidence bundles.

Example:

```text
data/reviews/leet-2026-verbal-even/q14/
  source/
    question_crop.png
    passage_crop.png
  text/
    ocr_raw.txt
    verified_text.md
  review.json
```

For attempt self-review, use the attempt ID as the first path component:

```text
data/reviews/<attempt_id>/
  q14.review.json
  q21.review.json
  feedback_request.json
```

Each `qNN.review.json` keeps user and assistant layers separate:

```json
{
  "grading": {
    "selected_choice": 1,
    "correct_choice": 4,
    "is_correct": false
  },
  "user_self_review": {
    "reasoning_text": "",
    "current_reflection": "",
    "memory_confidence": "partial",
    "created_by": "user"
  },
  "assistant_feedback": {
    "diagnosis_text": "",
    "evidence": [],
    "provisional_error_tags": [],
    "correction_rule": "",
    "created_by": "assistant"
  },
  "user_resolution": {
    "status": "pending",
    "final_error_tags": [],
    "note": null,
    "created_by": "user"
  }
}
```

Assistant imports must not overwrite `user_self_review`. Provisional tags are
assistant suggestions only until the user accepts or edits them in
`user_resolution`.

### `data/retry_attempts/`

Local results submitted after solving a generated retry PDF.

```text
data/retry_attempts/
  retry-20260713-143000-a1b2c3d4e5.json
```

Each file is keyed by the immutable session ID stored in the PDF's matching
manifest under `output/pdf/retry-pdfs/`. It contains session timestamps and one
item per selected review file:

```json
{
  "schema_version": 1,
  "session_id": "retry-20260713-143000-a1b2c3d4e5",
  "manifest_path": "output/pdf/retry-pdfs/retry-20260713-143000.json",
  "title": "LEET 오답 재풀이",
  "created_at": "2026-07-13T05:30:00+00:00",
  "updated_at": "2026-07-13T05:30:00+00:00",
  "items": [
    {
      "review_file": "data/reviews/<attempt_id>/q14.review.json",
      "question_id": "leet-2026-reasoning-even-q14",
      "year": 2026,
      "section": "추리논증",
      "question_no": 14,
      "selected_choice": 2,
      "correct_choice": 4,
      "outcome": "incorrect",
      "answered_at": "2026-07-13T05:30:00+00:00",
      "note": "조건의 예외를 다시 확인할 것"
    }
  ]
}
```

`outcome` is `correct`, `incorrect`, or `skipped`; a blank submitted choice is
the only way to produce `skipped`. Saving the same session ID again atomically
replaces that session file while preserving `created_at`. Recommendation status
is aggregated by `review_file`, with the most recent result controlling whether
the question is prioritized or excluded.

This directory contains personal answers, notes, and learning history. It is
ignored by Git and Graphify and should not be shared as source data.

## Evidence bundle principle

For a wrong-answer review, preserve both:

1. source evidence image, and
2. verified text.

The image is the source-of-truth artifact. The verified text is the analysis layer used for search, tagging, and LLM-assisted review.
