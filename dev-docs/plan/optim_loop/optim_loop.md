# OCR 최적화 Loop 계획: 측정 신뢰도와 기본값 채택 검증

## Summary

- 1차 목표는 `2022 추리논증 1-20` 기준 `ocr_seconds` **30% 이상 단축**이다.
- baseline은 loop 시작 시 같은 환경에서 cold/warm으로 재측정하며, 기존 `385.458s`는 참고값으로만 사용한다.
- 채택은 속도, 구조 가드레일, text diff 가드레일을 모두 통과해야 한다.

## Key Changes

- `leet-practice ocr`에 실험 옵션을 노출한다:
  - `--dpi`
  - `--reuse-existing-images`
  - `--no-annotated-blocks`
  - `--ocr-batch-chunk-size`, 기본 `4`
  - `--paddle-text-det-limit-side-len`, 기본 `None`
  - `--paddle-text-recognition-batch-size`, 기본 `None`
- PaddleOCR 옵션 해석을 명시적으로 기록한다.
  - `requested_options`: 사용자가 요청한 값
  - `effective_options`: 실제 args/constructor에 반영된 값
  - `option_support`: 현재 PaddleOCR signature 기준 지원 여부
  - `paddle_text_det_limit_side_len`과 `paddle_text_recognition_batch_size`는 지원 버전에서만 적용한다.
- PaddleOCR cache key와 benchmark summary에 위 옵션들을 포함한다.
- benchmark helper를 추가해 ignored artifact 아래 `summary.json`/`summary.csv`를 저장한다.

## Measurement Loop

- Baseline:
  - cold baseline: fresh process, fresh run id, image reuse 없음.
  - warm baseline: 같은 benchmark process에서 PaddleOCR cache/model init 이후 측정.
  - 후보 비교의 primary metric은 warm `ocr_seconds`.
- `ocr_seconds`와 `total_seconds`는 항상 별도 판정한다.
  - OCR 엔진 후보는 `ocr_seconds`로 평가한다.
  - `--reuse-existing-images`, `--no-annotated-blocks`는 workflow 개선으로 별도 분류한다.
- Screening은 `"2022 추리논증" 1-5`에서 one-axis 변경으로 수행한다.
  - `dpi`: `300`, `270`, `240`
  - `ocr_batch_chunk_size`: `4`, `8`, `10`
  - `paddle_text_det_limit_side_len`: `None`, `4000`, `3584`, `3200`
  - `paddle_text_recognition_batch_size`: `None`, `32`, `64`
- Full benchmark 직전, 상위 single-axis 후보 2개를 결합한 composite 후보 1개를 추가 평가한다.
- Full benchmark는 baseline, 상위 후보 2개, composite 후보 1개를 `"2022 추리논증" 1-20`에서 실행한다.

## Quality Guardrails

- 구조 지표:
  - `processed_pages` 동일
  - `ocr_errors` 없음
  - `selected_anchors`/`suggestions` baseline과 동일
  - total row count가 baseline 대비 90% 미만이면 탈락
  - page-level row count가 어떤 페이지에서든 baseline 대비 85% 미만이면 탈락
- OCR text normalization:
  - 공백 정규화
  - 줄바꿈 정규화
  - control character 제거
- Text diff 지표:
  - total normalized char count가 baseline 대비 90% 미만이면 탈락
  - page-level normalized char count가 어떤 페이지에서든 baseline 대비 85% 미만이면 탈락
  - page-level text similarity가 0.70 미만이면 탈락
  - page-level text similarity가 0.70 이상 0.80 미만이면 warning 기록
- Anchor 지표:
  - anchor question number sequence는 baseline과 동일해야 한다.
  - `selected_anchor_texts`와 `selected_anchor_y_positions`를 기록한다.
  - 큰 anchor text drift 또는 y-position drift는 warning으로 기록하고, question number sequence가 깨지면 탈락한다.
- `dpi` 또는 `paddle_text_det_limit_side_len` 변경 후보는 구조 가드레일을 통과해도 text diff가 크면 채택하지 않는다.

## Default Adoption

- CLI 옵션으로만 채택하는 경우 primary full benchmark 통과로 충분하다.
- 기본값 변경 후보는 primary full benchmark 외에 다른 시험/연도/영역의 smoke benchmark를 1개 이상 통과해야 한다.
- 특히 `dpi` 또는 `paddle_text_det_limit_side_len` 변경은 cross-exam smoke benchmark 통과 전까지 기본값으로 채택하지 않는다.
- smoke benchmark는 짧은 페이지 범위로 실행하되, 동일한 구조/text/anchor 가드레일을 적용한다.

## Test Plan

- CLI/options:
  - 새 옵션이 `ocr_crops`까지 전달되는지 검증한다.
  - `ocr_batch_chunk_size`가 chunk 분할에 반영되는지 fake OCR runner로 검증한다.
  - `paddle_text_det_limit_side_len`과 `paddle_text_recognition_batch_size`가 지원 버전에서만 PaddleOCR constructor에 전달되는지 검증한다.
  - cache key에 두 PaddleOCR 옵션이 포함되는지 검증한다.
- Benchmark helper:
  - fake `suggestions.json` fixture로 `requested_options`, `effective_options`, `option_support` 기록을 검증한다.
  - cold/warm run 구분이 summary에 남는지 검증한다.
  - page-level row/char, normalized chars, text similarity, anchor sequence/y-position metrics 계산을 검증한다.
  - 품질 가드레일 통과/탈락/warning 판정을 fixture로 검증한다.
- Regression:
  - 기존 artifact filenames, per-column OCR JSON key set, `suggestions.json` top-level schema는 유지한다.
  - 각 구현 PR마다 `uv run pytest`를 실행한다.

## Assumptions

- 목표는 OCR 엔진 단계 개선이며, end-to-end workflow 개선은 별도 카테고리로 기록한다.
- baseline 품질 기준은 loop 시작 시 재측정한 `"2022 추리논증" 1-20` 결과다.
- 30% 단축 실패 시에도 20% 이상 단축 후보는 부분 성공으로 남기고, 기본값 채택 여부는 품질 가드레일과 smoke benchmark 통과 여부로 결정한다.
