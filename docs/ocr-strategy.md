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
