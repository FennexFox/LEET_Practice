from __future__ import annotations

import json

from leet_practice.ocr_benchmark import (
    adoption_decision,
    benchmark_record,
    collect_quality_metrics,
    compare_to_baseline,
    composite_candidate,
    default_screening_candidates,
    normalize_ocr_text,
    write_benchmark_summary,
)


def _payload(rows_by_page: dict[int, list[str]], anchors: list[int] | None = None) -> dict:
    rows = [
        {"page": page, "text": text}
        for page, texts in rows_by_page.items()
        for text in texts
    ]
    selected_anchors = [
        {
            "question_number": number,
            "text": f"{number}. question",
            "page": 1,
            "column": "left",
            "stream_y_start": float(number * 100),
        }
        for number in (anchors or [1, 2])
    ]
    return {
        "processed_pages": sorted(rows_by_page),
        "ocr_errors": [],
        "rows": rows,
        "selected_anchors": selected_anchors,
        "suggestions": [{"suggestion_id": f"q{number:02d}"} for number in (anchors or [1, 2])],
        "timings": {"ocr_seconds": 10.0, "total_seconds": 12.0},
        "options": {
            "requested_options": {"ocr_batch_chunk_size": 4},
            "effective_options": {"ocr_batch_chunk_size": 4},
            "option_support": {"paddle_text_recognition_batch_size": True},
        },
    }


def test_normalize_ocr_text_removes_controls_and_normalizes_whitespace() -> None:
    assert normalize_ocr_text(" a\tb\r\n\x00c  \n\n") == "a b\nc"


def test_collect_quality_metrics_records_page_text_and_anchor_sequence() -> None:
    metrics = collect_quality_metrics(_payload({1: ["1. A", "body"], 2: ["2. B"]}))

    assert metrics.row_count == 3
    assert metrics.page_row_counts == {"1": 2, "2": 1}
    assert metrics.selected_anchor_numbers == [1, 2]
    assert metrics.selected_anchor_y_positions["1:left:1"] == 100.0


def test_compare_to_baseline_fails_on_text_loss_and_anchor_drift() -> None:
    baseline = _payload({1: ["1. " + ("A" * 100)], 2: ["2. " + ("B" * 100)]}, anchors=[1, 2])
    candidate = _payload({1: ["1. A"], 2: ["3. C"]}, anchors=[1, 3])

    comparison = compare_to_baseline(baseline, candidate)

    assert comparison.status == "fail"
    assert "anchor_question_number_sequence_mismatch" in comparison.failures
    assert "total_normalized_char_count_below_threshold" in comparison.failures
    assert any(item.startswith("page_text_similarity_below_threshold:") for item in comparison.failures)


def test_benchmark_record_and_summary_write_requested_effective_support(tmp_path) -> None:
    baseline = _payload({1: ["1. A"], 2: ["2. B"]})
    candidate = _payload({1: ["1. A"], 2: ["2. B"]})
    record = benchmark_record(name="candidate", run_kind="candidate", payload=candidate, baseline_payload=baseline)

    assert record["status"] == "pass"
    assert record["requested_options"] == {"ocr_batch_chunk_size": 4}
    assert record["effective_options"] == {"ocr_batch_chunk_size": 4}
    assert record["option_support"] == {"paddle_text_recognition_batch_size": True}

    json_path, csv_path = write_benchmark_summary([record], tmp_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["records"][0]["name"] == "candidate"
    assert "candidate" in csv_path.read_text(encoding="utf-8")


def test_default_screening_candidates_are_one_axis_changes() -> None:
    candidates = default_screening_candidates()

    assert candidates[0] == {"name": "baseline", "options": {}}
    assert all(len(candidate["options"]) <= 1 for candidate in candidates)


def test_composite_candidate_combines_two_single_axis_candidates() -> None:
    composite = composite_candidate(
        {"name": "dpi=270", "options": {"dpi": 270}},
        {"name": "ocr_batch_chunk_size=8", "options": {"ocr_batch_chunk_size": 8}},
    )

    assert composite == {
        "name": "dpi=270+ocr_batch_chunk_size=8",
        "options": {"dpi": 270, "ocr_batch_chunk_size": 8},
    }


def test_composite_candidate_rejects_overlapping_axes() -> None:
    try:
        composite_candidate(
            {"name": "dpi=270", "options": {"dpi": 270}},
            {"name": "dpi=240", "options": {"dpi": 240}},
        )
    except ValueError as exc:
        assert "dpi" in str(exc)
    else:
        raise AssertionError("overlapping composite candidates should fail")


def test_adoption_decision_requires_smoke_for_default_changes() -> None:
    primary = {"status": "pass"}
    smoke = [{"status": "pass"}]

    assert adoption_decision(primary_record=primary, changed_options={"dpi"}, mode="cli_option") == {
        "adoptable": True,
        "reasons": [],
    }
    default_without_smoke = adoption_decision(primary_record=primary, changed_options={"dpi"}, mode="default")
    assert default_without_smoke["adoptable"] is False
    assert "smoke_benchmark_required" in default_without_smoke["reasons"]
    assert adoption_decision(
        primary_record=primary,
        changed_options={"dpi"},
        mode="default",
        smoke_records=smoke,
    ) == {"adoptable": True, "reasons": []}
