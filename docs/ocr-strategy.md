# OCR strategy

The project should not depend on perfect full-PDF parsing. LEET PDFs can vary by year and file generation method. Some files expose usable text; others behave like image-heavy PDFs where standard text extraction returns only fragments.

## Working assumptions

- Answer-key PDFs are usually much easier to parse than problem PDFs.
- Problem PDFs may require page rendering and OCR.
- Full-page OCR often fails because two-column layouts mix reading order.
- Wrong-answer review only requires reliable text for the missed questions, not necessarily the entire exam.

## Recommended pipeline

```text
PDF page
→ render at 300-400 dpi
→ split by column or crop by question
→ run OCR
→ save raw OCR output
→ compare with source image
→ manually verify text
→ store verified text for review
```

## Virtual reading stream for crop suggestions

Manual per-question bounding-box storage is not a useful primary strategy for
LEET problem PDFs because question positions do not repeat reliably across
years, subjects, or even adjacent pages. Instead, use OCR rows to build a
candidate reading stream from stable layout blocks:

```text
page-left content block
-> page-right content block
-> next page-left content block
-> next page-right content block
```

`tools/suggest_question_crops.py` implements this as a candidate-generation
step. It renders requested PDF pages, splits each page into left/right columns,
estimates each column's content box from non-header/footer OCR row boxes, maps
rows into a continuous `stream_y` coordinate system, and looks for conservative
question-number anchors plus LEET set-header anchors such as `[1~3]`.

Set-header anchors split the output into passage and question candidates. For a
set `[a~b]`, the passage candidate runs from the set header to question `a`
when that question anchor is found. Question candidates normally run from
question `n` to question `n+1`; the last question in a detected set runs to the
next set header when available, then falls back to the next selected question
anchor or stream end. A single candidate can naturally span a column or page
boundary.

The crop-suggestion tool writes compact per-column OCR JSON by default:
extracted rows, row bounding boxes, confidence, provenance, OCR status, and
minimal options. Full raw PaddleOCR payloads are intentionally omitted unless a
short debug run explicitly uses `--include-raw-paddle-payload`.

This is intentionally not authoritative extraction. OCR may miss a number,
misread a set header, or mistake another leading number for a question anchor.
Question-anchor scoring rejects common false positives from choices, inline
numbered fragments, years, quantities, and header/footer rows, but suggestions
must still be checked against the emitted source crop images before any text
moves into review or canonical data.

## OCR engine policy

Keep the OCR pipeline conceptually interchangeable, but keep project dependencies narrow.

Selected local OCR engine:

- `paddleocr`: current default for Korean LEET PDF OCR

Removed from project dependencies and the local OCR script:

- `tesseract` / `pytesseract`
- `easyocr`

Commercial OCR remains an optional later fallback if local OCR is insufficient.

## Validation criteria

OCR is usable only if it preserves or allows quick recovery of:

- question numbers
- choice boundaries
- `①②③④⑤` or equivalent choice numbering
- `ㄱㄴㄷㄹ` statement blocks
- table and formula layout where relevant
- left-to-right, top-to-bottom reading order within each column

## Review rule

Raw OCR must not be written to final review records as if it were verified source text. Store it as `ocr_raw`, then produce `verified_text` after human or LLM-assisted checking against the image crop.
