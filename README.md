# LEET Practice

LEET Practice is a local-first workspace for managing law-school entrance exam practice, answer checking, and wrong-answer review.

The project is designed around one principle: **the core learning data is not only the question, but the relationship between the question and the solver's actual decision process.**

## Goals

- Store official exam metadata, answer keys, attempts, and review records in a structured form.
- Keep original PDFs and OCR/rendered artifacts local, because they may be large, copyrighted, or noisy.
- Preserve wrong-answer evidence as image crops plus verified text, rather than trusting raw OCR output.
- Support later LLM-assisted review of repeated error patterns, question-type weaknesses, and exam-day correction rules.

## Non-goals for the first version

- Fully automatic parsing of every question from every PDF.
- Blind trust in OCR output.
- Public redistribution of official exam PDFs or extracted full-text question banks.
- A polished web app before the data model and review workflow are stable.

## Recommended workflow

1. Place official PDF files under `data/raw_pdfs/<exam_id>/` locally.
2. Register exam metadata and answer keys.
3. Enter an attempt answer string, such as `22542 52323 ...`.
4. Grade the attempt against the verified answer key.
5. For wrong answers only, create an evidence bundle:
   - page image or crop image
   - raw OCR output
   - manually verified text
   - user's actual reasoning
   - diagnosed error type
   - correction rule
6. Use accumulated review records to identify repeated patterns.

The v1 attempt-review workflow keeps this separate from OCR verification:

```powershell
leet-practice attempt-review create attempt-001 leet-2026-reasoning-even --answers "22542 52323"
leet-practice attempt-review grade attempt-001
leet-practice attempt-review regrade attempt-001 --answer 12=5 --answer 27=3
leet-practice attempt-review serve attempt-001
leet-practice attempt-review feedback-export attempt-001
leet-practice attempt-review feedback-import attempt-001 --file path/to/assistant_feedback.json
```

Attempt answers are stored in `data/attempts/<attempt_id>.json`. Wrong-answer
self-review records are stored as `data/reviews/<attempt_id>/qXXX.review.json`
with separate nested user self-review, assistant feedback, and user resolution
fields.

## Data policy

The repository tracks code, schemas, documentation, and empty directory placeholders. It intentionally does **not** track local PDFs, rendered page images, OCR artifacts, extracted copyrighted text, personal attempts, or review notes by default.

See [`docs/data-layout.md`](docs/data-layout.md) for the intended local directory structure.
See [`docs/verification-workbench.md`](docs/verification-workbench.md) for the
planned human verification interface that promotes OCR crop suggestions into
verified passage and question data.
See [`docs/attempt-review.md`](docs/attempt-review.md) for the attempt
self-review and assistant feedback handoff workflow.

## Initial directory map

```text
LEET_Practice/
  data/
    raw_pdfs/        # local official PDFs; ignored by Git
    rendered_pages/  # local PDF page images; ignored by Git
    ocr/             # local OCR outputs; ignored by Git
    verification/    # local human verification drafts; ignored by Git by default
    canonical/       # local verified exam/question data; ignored by Git by default
    attempts/        # local attempt records; ignored by Git by default
    reviews/         # local wrong-answer reviews; ignored by Git by default
  docs/
    data-layout.md
    ocr-strategy.md
  src/leet_practice/
    models.py
    cli.py
  tests/
```

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
```

The initial CLI is only a placeholder:

```bash
leet-practice --help
```

## Design direction

The project should grow in this order:

1. Exam and answer-key data model.
2. Attempt input and grading.
3. Wrong-answer evidence bundles.
4. Verified-text review workflow.
5. Metadata tagging for question type, topic, difficulty, and error type.
6. LLM-facing query layer for pattern analysis.
7. Optional Streamlit or web UI.
