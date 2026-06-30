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
data/raw_pdfs/leet-2026-verbal-even/
  paper.pdf
  answers.pdf
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
  q001_ocr_raw.txt
```

OCR output is never treated as final truth. It must be reviewed before becoming verified text.

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

### `data/reviews/`

Wrong-answer reviews and evidence bundles.

Example:

```text
data/reviews/leet-2026-verbal-even/q014/
  source/
    question_crop.png
    passage_crop.png
  text/
    ocr_raw.txt
    verified_text.md
  review.json
```

## Evidence bundle principle

For a wrong-answer review, preserve both:

1. source evidence image, and
2. verified text.

The image is the source-of-truth artifact. The verified text is the analysis layer used for search, tagging, and LLM-assisted review.
