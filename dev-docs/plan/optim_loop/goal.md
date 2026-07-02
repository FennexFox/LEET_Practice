# OCR Optimization Loop Goal

## Objective

Run the OCR optimization loop enabled by `optim_loop.md` and produce an evidence-backed recommendation for reducing OCR stage runtime.

This goal is not complete when benchmark tooling exists. It is complete only after the loop has been executed, summarized, and a candidate outcome has been accepted or explicitly rejected with evidence.

## Primary Target

- Primary benchmark: `leet-practice ocr "2022 추리논증" 1-20`
- Primary metric: warm `ocr_seconds`
- Success target: at least 30% reduction from the loop-start warm baseline
- Minimum useful result: at least 20% reduction from the loop-start warm baseline
- Current historical reference only: `ocr_seconds = 385.458s`

The historical reference must not be used as the baseline for adoption. Re-measure baseline at loop start on the same machine and branch.

## Required Measurement Artifacts

Create an ignored artifact directory under:

```text
artifacts/ocr_benchmarks/<run-id>/
```

It must contain:

- `summary.json`
- `summary.csv`
- references to every baseline, screening, full, composite, and smoke `suggestions.json`
- explicit cold/warm labels for baseline and candidates
- `requested_options`, `effective_options`, and `option_support` for every run

`ocr_seconds` and `total_seconds` must be recorded separately. Improvements from `--reuse-existing-images` or `--no-annotated-blocks` are workflow improvements and must not be counted as OCR engine improvements.

## Execution Plan

1. Re-measure baseline on `2022 추리논증 1-20`.
   - cold baseline: fresh process, fresh run id, no image reuse
   - warm baseline: same benchmark process after PaddleOCR/model initialization
   - primary comparison baseline: warm `ocr_seconds`

2. Run screening on `2022 추리논증 1-5`.
   - one-axis changes only
   - candidates:
     - `dpi`: `300`, `270`, `240`
     - `ocr_batch_chunk_size`: `4`, `8`, `10`
     - `paddle_text_det_limit_side_len`: `None`, `4000`, `3584`, `3200`
     - `paddle_text_recognition_batch_size`: `None`, `32`, `64`

3. Select full benchmark candidates.
   - choose the top two passing single-axis candidates by warm `ocr_seconds`
   - add one composite candidate combining those two, only if their changed option axes do not overlap

4. Run full benchmark on `2022 추리논증 1-20`.
   - baseline
   - top two candidates
   - composite candidate

5. Run smoke benchmark before any default change.
   - required for any default-value change
   - mandatory for `dpi` or `paddle_text_det_limit_side_len`
   - use at least one different exam/year/section with a short page range
   - apply the same structural, text, and anchor guardrails

6. Produce final recommendation.
   - `adopt_cli_option`: primary full benchmark passes; no default change
   - `adopt_default`: primary full benchmark and smoke benchmark pass
   - `partial_success`: 20%+ but under 30%, with guardrails passing
   - `reject`: speed or quality criteria fail

## Quality Gates

Every candidate must be compared to the loop-start baseline.

Hard failures:

- `processed_pages` differs
- `ocr_errors` is non-empty
- `selected_anchors` count differs
- `suggestions` count differs
- anchor question number sequence differs
- total row count is below 90% of baseline
- any page-level row count is below 85% of baseline
- total normalized char count is below 90% of baseline
- any page-level normalized char count is below 85% of baseline
- any page-level text similarity is below 0.70

Warnings:

- any page-level text similarity is at least 0.70 and below 0.80
- selected anchor text or y-position drift is visible while question number sequence remains intact

Normalization for text comparison:

- remove control characters
- normalize CRLF/CR to LF
- normalize repeated inline whitespace
- trim and drop empty lines

## Completion Checklist

The goal is complete only when all items are true:

- Baseline was re-measured at loop start with cold and warm labels.
- Screening was run or explicitly skipped with a documented reason.
- Top two single-axis candidates and one composite candidate were evaluated, unless fewer than two candidates passed screening.
- Full benchmark summary exists under `artifacts/ocr_benchmarks/<run-id>/`.
- Quality gates were evaluated from summary data, not by visual inspection alone.
- If recommending a default change, at least one cross-exam smoke benchmark passed.
- A final recommendation is documented with one of:
  - `adopt_cli_option`
  - `adopt_default`
  - `partial_success`
  - `reject`
- The final recommendation states the measured baseline, measured candidate runtime, percentage change, selected options, and quality gate result.

## Non-Goals

- Do not change OCR defaults solely from screening results.
- Do not count image reuse or annotated image skipping as OCR engine improvement.
- Do not accept `dpi` or `paddle_text_det_limit_side_len` as defaults without cross-exam smoke evidence.
- Do not use historical `385.458s` as the adoption baseline.

## Validation Commands

Before and after loop-related code changes:

```powershell
uv run pytest
```

After benchmark runs:

```powershell
leet-practice ocr-benchmark-summary `
  <baseline-suggestions.json> `
  --candidate <candidate-suggestions.json> `
  --out-dir artifacts/ocr_benchmarks/<run-id>
```
