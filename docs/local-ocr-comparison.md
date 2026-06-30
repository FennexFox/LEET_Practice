# Local OCR comparison

Use `tools/compare_ocr_engines.py` to run PaddleOCR on LEET page images or rendered PDF pages.

Use `tools/suggest_question_crops.py` for the next automation step: generating
candidate question crop suggestions from OCR rows in page-column reading order.

## Install dependencies with uv

Install PDF rendering plus the PaddleOCR Python package:

```bash
uv sync --extra pdf --extra ocr
```

Install the PaddlePaddle runtime separately. This is intentional: CPU and GPU builds use different package names, and Windows GPU wheels require a custom package index.

For the current Windows GPU workflow, keep PyTorch CPU-only and install the Paddle GPU runtime:

```powershell
uv pip install "paddlepaddle-gpu==3.2.2" -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
```

For CPU-only fallback, install the tested Paddle CPU runtime instead:

```powershell
uv pip install "paddlepaddle==3.1.1"
```

## Recommended first test

Place a local PDF here:

```text
data/raw_pdfs/leet-2026-verbal-even/paper.pdf
```

Then run:

```powershell
uv run python tools/compare_ocr_engines.py `
  --pdf "data/raw_pdfs/leet-2026-verbal-even/paper.pdf" `
  --page 1 `
  --split-columns
```

For the Windows GPU workflow, use:

```powershell
uv run python tools/compare_ocr_engines.py `
  --pdf "data/raw_pdfs/leet-2026-verbal-even/paper.pdf" `
  --page 1 `
  --split-columns `
  --paddle-device gpu:0 `
  --paddle-preimport-paddle
```

The script writes outputs under:

```text
artifacts/ocr_compare/<timestamp>/
```

Typical outputs:

```text
page_001_300dpi.png
crop_left.png
crop_right.png
left.paddleocr.txt
left.paddleocr.json
right.paddleocr.txt
right.paddleocr.json
manifest.json
```

`artifacts/` is ignored by Git.

## Suggest candidate question crops

After PaddleOCR is installed and working, run the question crop suggestion tool
over a page range:

```powershell
uv run python tools/suggest_question_crops.py `
  --pdf "data/raw_pdfs/leet-2026-verbal-even/paper.pdf" `
  --pages 1-10 `
  --run-id leet-2026-verbal-even-p001-010 `
  --paddle-device gpu:0 `
  --paddle-preimport-paddle
```

The tool renders each requested page, splits it into left and right content
blocks, runs PaddleOCR on each block, and builds a virtual reading stream:

```text
page 1 left -> page 1 right -> page 2 left -> page 2 right -> ...
```

It then looks for conservative question-number anchors and LEET set-header
anchors such as `[1~3]`. Set headers are used to emit passage candidates from
the set header to the first question in that set, and to stop the last question
in a set at the next set header when possible. When a candidate crosses a
column or page boundary, the output keeps separate source crop parts and also
writes a stitched preview image for quick review.

Outputs are written under:

```text
artifacts/question_crop_suggestions/<timestamp>/
```

Typical outputs:

```text
page_001_300dpi.png
page_001_left.png
page_001_left.paddleocr.json
p001_left_annotated.png
set_01_03_passage_candidate/
  part_01_p001_left.png
  set_01_03_passage_candidate_preview.png
q01_candidate/
  part_01_p001_left.png
  q01_candidate_preview.png
suggestions.json
```

The per-column `*.paddleocr.json` files are compact by default. They contain
extracted OCR rows, row bounding boxes, confidence, page/column provenance, OCR
status, and minimal options, but not PaddleOCR's full raw internal payload. Use
`--include-raw-paddle-payload` only for short debug runs where the large raw
payload is intentionally needed.

The tool processes pages incrementally. If a run is interrupted, it writes a
partial `suggestions.json` for completed OCR blocks when possible and marks it
with `status: partial_interrupted`. Retry with the same `--run-id`; by default
`--reuse-existing-images` reuses rendered page and column PNGs already present
in that run directory.

Every item in `suggestions.json` is labeled as a candidate or suggestion and
contains provenance back to page, column, source image, local crop coordinates,
and source-page coordinates. These outputs are evidence for review, not
verified question text.

## Test an existing image

```powershell
uv run python tools/compare_ocr_engines.py `
  --image "artifacts/sample_page.png" `
  --split-columns
```

## If PaddleOCR language fails

The default PaddleOCR language is `korean`. If that fails in the installed version, try:

```powershell
uv run python tools/compare_ocr_engines.py `
  --pdf "data/raw_pdfs/leet-2026-verbal-even/paper.pdf" `
  --page 1 `
  --paddle-lang ko
```

## If PaddleOCR fails with oneDNN/PIR runtime errors

On Windows CPU environments, PaddleOCR can fail inside PaddlePaddle/oneDNN with errors similar to:

```text
ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]
```

The script disables Paddle MKLDNN/oneDNN and PIR paths by default before importing PaddleOCR. It also disables document orientation/unwarping/textline-orientation helper models when the installed PaddleOCR version supports those constructor flags.

If you want to test the raw PaddleOCR defaults again, explicitly re-enable them:

```powershell
uv run python tools/compare_ocr_engines.py `
  --pdf "data/raw_pdfs/leet-2026-verbal-even/paper.pdf" `
  --page 1 `
  --split-columns `
  --no-paddle-disable-mkldnn `
  --no-paddle-disable-pir `
  --no-paddle-disable-doc-preprocess
```

## Windows DLL load-order notes

On Windows, `paddle` and `torch` can conflict depending on native DLL load order. The most stable OCR-oriented combination found so far is:

```text
Torch CPU
→ Paddle GPU
→ PaddleOCR
```

Use `--paddle-preimport-paddle` and keep the default torch pre-import enabled so the script loads `torch` first, then `paddle`, then PaddleOCR.

## If full-page order looks mixed

This is expected for two-column test papers. Use column crops:

```powershell
--split-columns
```

If the crop cuts off text, adjust ratios:

```powershell
--crop-top 0.04 --crop-bottom 0.95 --crop-left 0.04 --crop-right 0.96 --center-gutter 0.015
```

## What to evaluate

Do not judge only by character accuracy. For LEET wrong-answer review, evaluate whether the OCR preserves or quickly recovers:

- question numbers
- choice boundaries
- `①②③④⑤`
- `ㄱㄴㄷㄹ` blocks
- table/formula structure
- left-column then right-column reading order

The best OCR setup is the one that minimizes verification time for missed questions, not necessarily the one with the highest raw character match rate.
