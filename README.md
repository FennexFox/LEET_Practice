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
    retry_attempts/  # local retry-PDF results; ignored by Git by default
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

## Tagging dashboard

Run the live local dashboard when reviewing provisional tags:

```bash
python tools/serve_tagging_dashboard.py
```

Open `http://127.0.0.1:8765/`. The server reads `data/tagging/*.jsonl` and
tag dictionary Markdown files on each request, so refresh the browser after
editing local tagging data. The same live payload is available at
`/api/dashboard`.

For a standalone snapshot, regenerate the static HTML file:

```bash
python tools/build_tagging_dashboard.py
```

The live dashboard can also build a printable retry workbook. Apply the
filters, use **추천 선택** for a balanced selection across vulnerable primary
tags, adjust the checkboxes, and choose **Generate retry PDF**. The workbook
keeps questions and choices in the first section and puts answers, previous
choices, and error-tag analysis in a separate appendix.

Each generated workbook has a session ID and a matching manifest. After it is
generated, open **결과 입력**, enter one answer per question, and save the
session. A blank answer is recorded as `skipped`; filled answers are graded
locally against the manifest. The result-entry page does not reveal the answer
key until the session has been submitted.

You do not need to keep the generation tab open. Return to **기존 재풀이 결과
입력** later and enter either the full session ID printed on the PDF's first
page or its final 10-character code. The live dashboard also lists recent
generated sessions and whether results have been submitted. If the short code
matches more than one session, use the full ID.

If a workbook was generated by mistake, choose **세션 삭제** in the recent
session list. For a session outside the recent list, enter its full ID and use
**전체 ID로 삭제**; short codes cannot delete sessions. After confirmation,
the generated PDF, its manifest, and that session's saved result are permanently
removed together. Deleting a submitted session also removes it from retry-status
calculations, so any remaining older attempt becomes the latest status for those
questions. To correct answer-entry mistakes without deleting the workbook,
reopen the session and submit it again.

The next recommendation orders candidates by latest retry state: incorrect,
skipped, then never retried. Questions whose latest retry answer is correct are
excluded by default, including from an explicit selection. Enable **Include
completed** to include them again. Objective difficulty is not used in this
retry-history policy; the existing tag-balanced ordering still distributes
questions across vulnerable primary tags. Within each retry-state tier, the
balanced selection prefers older self-review input and emits the selected
questions from older to newer, so recently entered reviews appear later.

The same generator is available from the CLI:

```bash
python -m pip install -e ".[pdf]"
leet-practice retry-pdf --limit 20
leet-practice retry-pdf --tag CHOICE_VERIFICATION_FAILURE --year 2025
leet-practice retry-pdf --review-file "data/reviews/<attempt>/q01.review.json"
leet-practice retry-pdf --include-completed
```

PDFs and their reproducibility manifests are written together under
`output/pdf/retry-pdfs/` by default. Use `--font` when a Korean system font
cannot be discovered automatically. Saved session results are written to
`data/retry_attempts/<session_id>.json`; this personal study data is ignored by
Git and Graphify. Submitting the same session again replaces its saved answers
instead of adding a duplicate attempt. Session lookup remains available across
dashboard-server restarts as long as the matching manifest remains under
`output/pdf/retry-pdfs/`.

## Design direction

The project should grow in this order:

1. Exam and answer-key data model.
2. Attempt input and grading.
3. Wrong-answer evidence bundles.
4. Verified-text review workflow.
5. Metadata tagging for question type, topic, difficulty, and error type.
6. LLM-facing query layer for pattern analysis.
7. Optional Streamlit or web UI.
