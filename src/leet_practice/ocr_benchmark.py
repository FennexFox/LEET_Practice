"""Benchmark helpers for OCR optimization loops."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
PAGE_CHAR_RATIO_MIN = 0.85
TOTAL_CHAR_RATIO_MIN = 0.90
PAGE_ROW_RATIO_MIN = 0.85
TOTAL_ROW_RATIO_MIN = 0.90
PAGE_TEXT_SIMILARITY_FAIL = 0.70
PAGE_TEXT_SIMILARITY_WARN = 0.80
DEFAULT_ADOPTION_SMOKE_OPTIONS = {"dpi", "paddle_text_det_limit_side_len"}


@dataclass(frozen=True)
class OcrQualityMetrics:
    processed_pages: list[int]
    ocr_error_count: int
    row_count: int
    page_row_counts: dict[str, int]
    normalized_total_chars: int
    per_page_char_count: dict[str, int]
    selected_anchor_numbers: list[int]
    selected_anchor_texts: list[str]
    selected_anchor_y_positions: dict[str, float]
    suggestions_count: int
    per_page_text: dict[str, str] = field(repr=False)


@dataclass(frozen=True)
class OcrBenchmarkComparison:
    status: str
    failures: list[str]
    warnings: list[str]
    metrics: OcrQualityMetrics


def normalize_ocr_text(text: str) -> str:
    cleaned = CONTROL_CHARS_RE.sub("", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "\n".join(WHITESPACE_RE.sub(" ", line).strip() for line in cleaned.split("\n"))
    cleaned = "\n".join(line for line in cleaned.split("\n") if line)
    return cleaned


def page_key(page: Any) -> str:
    try:
        return str(int(page))
    except (TypeError, ValueError):
        return str(page)


def collect_quality_metrics(payload: dict[str, Any]) -> OcrQualityMetrics:
    page_text_parts: dict[str, list[str]] = {}
    page_row_counts: dict[str, int] = {}
    for row in payload.get("rows") or []:
        key = page_key(row.get("page"))
        text = str(row.get("text") or "")
        page_text_parts.setdefault(key, []).append(text)
        page_row_counts[key] = page_row_counts.get(key, 0) + 1

    per_page_text = {key: normalize_ocr_text("\n".join(parts)) for key, parts in page_text_parts.items()}
    per_page_char_count = {key: len(text) for key, text in per_page_text.items()}
    total_text = normalize_ocr_text("\n".join(per_page_text[key] for key in sorted(per_page_text, key=_sort_key)))

    selected_anchors = payload.get("selected_anchors") or []
    selected_anchor_numbers: list[int] = []
    selected_anchor_texts: list[str] = []
    selected_anchor_y_positions: dict[str, float] = {}
    for anchor in selected_anchors:
        try:
            question_number = int(anchor.get("question_number"))
        except (TypeError, ValueError):
            continue
        selected_anchor_numbers.append(question_number)
        selected_anchor_texts.append(str(anchor.get("text") or ""))
        key = f"{anchor.get('page')}:{anchor.get('column')}:{question_number}"
        try:
            selected_anchor_y_positions[key] = float(anchor.get("stream_y_start"))
        except (TypeError, ValueError):
            pass

    return OcrQualityMetrics(
        processed_pages=[int(page) for page in payload.get("processed_pages") or []],
        ocr_error_count=len(payload.get("ocr_errors") or []),
        row_count=len(payload.get("rows") or []),
        page_row_counts=page_row_counts,
        normalized_total_chars=len(total_text),
        per_page_char_count=per_page_char_count,
        selected_anchor_numbers=selected_anchor_numbers,
        selected_anchor_texts=selected_anchor_texts,
        selected_anchor_y_positions=selected_anchor_y_positions,
        suggestions_count=len(payload.get("suggestions") or []),
        per_page_text=per_page_text,
    )


def compare_to_baseline(baseline_payload: dict[str, Any], candidate_payload: dict[str, Any]) -> OcrBenchmarkComparison:
    baseline = collect_quality_metrics(baseline_payload)
    candidate = collect_quality_metrics(candidate_payload)
    failures: list[str] = []
    warnings: list[str] = []

    if candidate.processed_pages != baseline.processed_pages:
        failures.append("processed_pages_mismatch")
    if candidate.ocr_error_count:
        failures.append("ocr_errors_present")
    if candidate.suggestions_count != baseline.suggestions_count:
        failures.append("suggestions_count_mismatch")
    if candidate.selected_anchor_numbers != baseline.selected_anchor_numbers:
        failures.append("anchor_question_number_sequence_mismatch")
    if _ratio(candidate.row_count, baseline.row_count) < TOTAL_ROW_RATIO_MIN:
        failures.append("total_row_count_below_threshold")
    if _ratio(candidate.normalized_total_chars, baseline.normalized_total_chars) < TOTAL_CHAR_RATIO_MIN:
        failures.append("total_normalized_char_count_below_threshold")

    for page, baseline_count in baseline.page_row_counts.items():
        if _ratio(candidate.page_row_counts.get(page, 0), baseline_count) < PAGE_ROW_RATIO_MIN:
            failures.append(f"page_row_count_below_threshold:{page}")
    for page, baseline_count in baseline.per_page_char_count.items():
        if _ratio(candidate.per_page_char_count.get(page, 0), baseline_count) < PAGE_CHAR_RATIO_MIN:
            failures.append(f"page_char_count_below_threshold:{page}")
        similarity = text_similarity(baseline.per_page_text.get(page, ""), candidate.per_page_text.get(page, ""))
        if similarity < PAGE_TEXT_SIMILARITY_FAIL:
            failures.append(f"page_text_similarity_below_threshold:{page}:{similarity:.3f}")
        elif similarity < PAGE_TEXT_SIMILARITY_WARN:
            warnings.append(f"page_text_similarity_warning:{page}:{similarity:.3f}")

    return OcrBenchmarkComparison(
        status="fail" if failures else "pass",
        failures=failures,
        warnings=warnings,
        metrics=candidate,
    )


def text_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def benchmark_record(
    *,
    name: str,
    run_kind: str,
    payload: dict[str, Any],
    baseline_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comparison = (
        compare_to_baseline(baseline_payload, payload)
        if baseline_payload is not None
        else OcrBenchmarkComparison("baseline", [], [], collect_quality_metrics(payload))
    )
    options = payload.get("options") or {}
    timings = payload.get("timings") or {}
    return {
        "name": name,
        "run_kind": run_kind,
        "status": comparison.status,
        "failures": comparison.failures,
        "warnings": comparison.warnings,
        "ocr_seconds": timings.get("ocr_seconds"),
        "total_seconds": timings.get("total_seconds"),
        "requested_options": options.get("requested_options") or {},
        "effective_options": options.get("effective_options") or {},
        "option_support": options.get("option_support") or {},
        "metrics": asdict(comparison.metrics),
    }


def write_benchmark_summary(records: list[dict[str, Any]], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "summary.json"
    csv_path = out_dir / "summary.csv"
    json_path.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "run_kind",
                "status",
                "ocr_seconds",
                "total_seconds",
                "row_count",
                "normalized_total_chars",
                "suggestions_count",
                "failures",
                "warnings",
            ],
        )
        writer.writeheader()
        for record in records:
            metrics = record["metrics"]
            writer.writerow(
                {
                    "name": record["name"],
                    "run_kind": record["run_kind"],
                    "status": record["status"],
                    "ocr_seconds": record["ocr_seconds"],
                    "total_seconds": record["total_seconds"],
                    "row_count": metrics["row_count"],
                    "normalized_total_chars": metrics["normalized_total_chars"],
                    "suggestions_count": metrics["suggestions_count"],
                    "failures": ";".join(record["failures"]),
                    "warnings": ";".join(record["warnings"]),
                }
            )
    return json_path, csv_path


def default_screening_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = [{"name": "baseline", "options": {}}]
    axes = {
        "dpi": [270, 240],
        "ocr_batch_chunk_size": [8, 10],
        "paddle_text_det_limit_side_len": [4000, 3584, 3200],
        "paddle_text_recognition_batch_size": [32, 64],
    }
    for option, values in axes.items():
        for value in values:
            candidates.append({"name": f"{option}={value}", "options": {option: value}})
    return candidates


def composite_candidate(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_options = dict(first.get("options") or {})
    second_options = dict(second.get("options") or {})
    overlap = set(first_options) & set(second_options)
    if overlap:
        raise ValueError(f"Composite candidates must not overlap option axes: {sorted(overlap)}")
    options = {**first_options, **second_options}
    name = "+".join(part for part in (str(first.get("name") or ""), str(second.get("name") or "")) if part)
    return {"name": name or "composite", "options": options}


def adoption_decision(
    *,
    primary_record: dict[str, Any],
    changed_options: set[str],
    mode: str,
    smoke_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    smoke_records = smoke_records or []
    if primary_record.get("status") != "pass":
        reasons.append("primary_benchmark_failed")
    if mode == "cli_option":
        return {"adoptable": not reasons, "reasons": reasons}
    if mode != "default":
        reasons.append(f"unknown_adoption_mode:{mode}")
        return {"adoptable": False, "reasons": reasons}
    if not smoke_records:
        reasons.append("smoke_benchmark_required")
    elif any(record.get("status") != "pass" for record in smoke_records):
        reasons.append("smoke_benchmark_failed")
    if changed_options & DEFAULT_ADOPTION_SMOKE_OPTIONS and not smoke_records:
        reasons.append("cross_exam_smoke_required_for_input_scale_option")
    return {"adoptable": not reasons, "reasons": reasons}


def _ratio(value: int, baseline: int) -> float:
    if baseline <= 0:
        return 1.0 if value >= baseline else 0.0
    return value / baseline


def _sort_key(value: str) -> tuple[int, str]:
    try:
        return (0, f"{int(value):09d}")
    except ValueError:
        return (1, value)
