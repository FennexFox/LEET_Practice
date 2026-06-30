# Local OCR comparison

Use `tools/compare_ocr_engines.py` to run PaddleOCR on LEET page images or rendered PDF pages.

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
