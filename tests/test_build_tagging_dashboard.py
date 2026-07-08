from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "tools" / "build_tagging_dashboard.py"
DASHBOARD_PATH = ROOT / "docs" / "tagging-dashboard.html"
RECORDS_PATH = ROOT / "data" / "tagging" / "provisional_tags.jsonl"


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


def test_dashboard_counts_match_tagging_jsonl():
    records = load_records()

    assert len(records) == 89
    assert sum(record["use_for_tag_frequency"] is True for record in records) == 84
    assert sum(record["holdout"] is True for record in records) == 5
    assert (
        sum(
            record["needs_review"] is True and record["holdout"] is not True
            for record in records
        )
        == 2
    )


def test_holdouts_excluded_from_frequency_and_promotion():
    records = load_records()
    holdouts = [record for record in records if record["holdout"] is True]
    expected_files = {
        "data/reviews/2025 추리논증 짝수형/q09.review.json",
        "data/reviews/2025 추리논증 짝수형/q23.review.json",
        "data/reviews/2025 추리논증 짝수형/q29.review.json",
        "data/reviews/2025 추리논증 짝수형/q33.review.json",
        "data/reviews/2025 추리논증 짝수형/q34.review.json",
    }

    assert {record["review_file"] for record in holdouts} == expected_files
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


def test_dashboard_frequency_after_v1_corrections():
    records = load_records()
    active = [record for record in records if record["use_for_tag_frequency"] is True]
    counts = Counter(record["provisional_tags"]["primary"] for record in active)

    assert counts["SCOPE_CONDITION_MISAPPLICATION"] == 16
    assert counts["CONCEPT_LAYER_CONFUSION"] == 12
    assert counts["TABLE_DIAGRAM_ENCODING_ERROR"] == 7
    assert counts["RELATION_DIRECTION_REVERSAL"] == 3
    assert counts["TEXTUAL_REDEFINITION_MISSED"] == 3
    assert counts["UNWARRANTED_ASSUMPTION_ADDED"] == 3
    assert "INSUFFICIENT_REVIEW_BASIS" not in counts
