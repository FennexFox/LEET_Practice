from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from http import HTTPStatus
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "tools" / "build_tagging_dashboard.py"
DASHBOARD_PATH = ROOT / "docs" / "tagging-dashboard.html"
RECORDS_PATH = ROOT / "data" / "tagging" / "provisional_tags.jsonl"
TOOLS_DIR = ROOT / "tools"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_tagging_dashboard", BUILDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_records() -> list[dict]:
    return [
        json.loads(line)
        for line in RECORDS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_dashboard_builder_generates_html():
    builder = load_builder()
    builder.main()

    assert DASHBOARD_PATH.exists()
    html = DASHBOARD_PATH.read_text(encoding="utf-8")
    for section_id in builder.SECTION_IDS:
        assert f'<section id="{section_id}"' in html
    assert "/review?file=" in html


def test_dashboard_counts_match_tagging_jsonl():
    records = load_records()

    assert len(records) == 95
    assert sum(record["use_for_tag_frequency"] is True for record in records) == 90
    assert sum(record["holdout"] is True for record in records) == 5
    assert (
        sum(
            record["needs_review"] is True and record["holdout"] is not True
            for record in records
        )
        == 1
    )


def test_holdouts_excluded_from_frequency_and_promotion():
    records = load_records()
    holdouts = [record for record in records if record["holdout"] is True]
    expected_qnos = {"q09", "q23", "q29", "q33", "q34"}

    assert {Path(record["review_file"]).stem.split(".")[0] for record in holdouts} == expected_qnos
    assert all(record["review_file"].startswith("data/reviews/2025 ") for record in holdouts)
    assert all(record["use_for_tag_frequency"] is False for record in holdouts)
    assert all(record["use_for_final_tag_promotion"] is False for record in holdouts)
    assert all(record["revisit_plan"] == "resolve_after_retake" for record in holdouts)


def test_dashboard_includes_v1_tag_sets():
    builder = load_builder()
    builder.main()
    html = DASHBOARD_PATH.read_text(encoding="utf-8")

    for tag_id in builder.FINAL_V1_TAGS:
        assert tag_id in html
    for tag_id in builder.SUPPORTING_STATUS_TAGS:
        assert tag_id in html


def test_dashboard_review_links_use_readable_labels_and_scrollable_final_cards():
    builder = load_builder()
    payload = builder.build_dashboard_data()
    html = builder.build_current_dashboard_html()

    assert "2020 언어이해 홀수형 q16</a>" in html
    assert "tag-card-cases" in html

    tag_id = "SCOPE_CONDITION_MISAPPLICATION"
    expected_cases = len(builder.select_representative_cases(payload["records"], tag_id, limit=None))
    final_section = html.split('<section id="final-tags">', 1)[1]
    card = final_section.split(f'<span class="tag-badge final">{tag_id}</span>', 1)[1].split("</article>", 1)[0]

    assert card.count("/review?file=") == expected_cases
    assert expected_cases > 3


def test_dashboard_frequency_after_v1_corrections():
    records = load_records()
    active = [record for record in records if record["use_for_tag_frequency"] is True]
    counts = Counter(record["provisional_tags"]["primary"] for record in active)

    assert counts["SCOPE_CONDITION_MISAPPLICATION"] == 17
    assert counts["CONCEPT_LAYER_CONFUSION"] == 14
    assert counts["TABLE_DIAGRAM_ENCODING_ERROR"] == 10
    assert counts["RELATION_DIRECTION_REVERSAL"] == 4
    assert counts["TEXTUAL_REDEFINITION_MISSED"] == 3
    assert counts["UNWARRANTED_ASSUMPTION_ADDED"] == 5
    assert "INSUFFICIENT_REVIEW_BASIS" not in counts


def test_dashboard_reads_correction_rules_from_v1_provisional_headings():
    builder = load_builder()
    metadata = builder.classify_tags()

    correction_rule = metadata["SCOPE_CONDITION_MISAPPLICATION"]["correction_rule"]
    assert correction_rule
    assert "Confirm against representative cases" not in correction_rule
    assert correction_rule != metadata["SCOPE_CONDITION_MISAPPLICATION"]["definition"]


def test_dashboard_data_builder_matches_jsonl():
    builder = load_builder()
    payload = builder.build_dashboard_data()

    assert payload["stats"]["total_records"] == len(load_records())
    assert len(payload["records"]) == payload["stats"]["total_records"]
    assert payload["tagFrequency"]
    assert payload["audit"]["jsonl_records_parsed"] == payload["stats"]["total_records"]


def test_live_dashboard_handler_serves_current_json():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    captured = {}

    class TestHandler(serve_tagging_dashboard.TaggingDashboardHandler):
        def __init__(self):
            pass

        def _send_bytes(self, body, content_type, status=HTTPStatus.OK):
            captured["body"] = body
            captured["content_type"] = content_type
            captured["status"] = status

    handler = TestHandler()
    handler._send_dashboard_json()

    payload = json.loads(captured["body"].decode("utf-8"))
    expected = serve_tagging_dashboard.dashboard.build_dashboard_data()
    assert captured["status"] == HTTPStatus.OK
    assert captured["content_type"] == "application/json; charset=utf-8"
    assert payload == expected


def test_live_dashboard_handler_serves_current_html():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    captured = {}

    class TestHandler(serve_tagging_dashboard.TaggingDashboardHandler):
        def __init__(self):
            pass

        def _send_bytes(self, body, content_type, status=HTTPStatus.OK):
            captured["body"] = body
            captured["content_type"] = content_type
            captured["status"] = status

    handler = TestHandler()
    handler._send_dashboard_html()

    html = captured["body"].decode("utf-8")
    assert captured["status"] == HTTPStatus.OK
    assert captured["content_type"] == "text/html; charset=utf-8"
    assert "LEET Tagging Dashboard" in html
    assert "95" in html


def test_live_review_page_shows_question_and_retry():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    records = load_records()
    record = next(
        item
        for item in records
        if item["review_file"].endswith("/q32.review.json") and item["year"] == 2019
    )
    html = serve_tagging_dashboard.build_review_page(record["review_file"])

    assert "Retry" in html
    assert "Canonical Question" in html
    assert "Original Review" in html
    assert "data-correct=\"3\"" in html
    assert record["review_file"] in html


def test_live_review_page_finds_abbreviated_canonical_directory():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    records = load_records()
    record = next(
        item
        for item in records
        if item["review_file"].endswith("/q05.review.json")
        and item["year"] == 2020
        and item["section"] == "\uc5b8\uc5b4\uc774\ud574"
    )
    html = serve_tagging_dashboard.build_review_page(record["review_file"])

    assert "Canonical question data was not found" not in html
    assert "Retry" in html
    assert "data-correct=\"5\"" in html
    assert html.index("Canonical Question") < html.index("Retry")


def test_live_review_page_rejects_outside_paths():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    with pytest.raises(ValueError):
        serve_tagging_dashboard.resolve_review_path("../README.md")
