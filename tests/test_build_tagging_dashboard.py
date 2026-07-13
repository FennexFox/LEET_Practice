from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace


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
    assert sum(record["use_for_tag_frequency"] is True for record in records) == 95
    assert sum(record["holdout"] is True for record in records) == 0
    assert (
        sum(
            record["needs_review"] is True and record["holdout"] is not True
            for record in records
        )
        == 1
    )


def test_2025_reasoning_retake_replaces_old_holdouts():
    records = load_records()
    retake = [
        record
        for record in records
        if record["review_file"].startswith("data/reviews/2025 추리논증 홀수형/")
    ]

    assert {Path(record["review_file"]).stem.split(".")[0] for record in retake} == {
        "q10",
        "q14",
        "q17",
        "q33",
        "q34",
    }
    assert all(record["exam_id"] == "2025 추리논증 홀수형" for record in retake)
    assert all(record["holdout"] is False for record in retake)
    assert all(record["use_for_tag_frequency"] is True for record in retake)
    assert all(record["use_for_final_tag_promotion"] is True for record in retake)
    assert not any(
        record["year"] == 2025
        and record["section"] == "추리논증"
        and "짝수형" in record["review_file"]
        for record in records
    )


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


def test_dashboard_polished_workspace_controls_and_frequency_bars():
    builder = load_builder()
    html = builder.build_current_dashboard_html()

    assert 'class="overview-intro"' in html
    assert 'class="frequency-track"' in html
    assert 'id="resetFilters"' in html
    assert 'aria-label="Dashboard sections"' in html
    assert "linked cases</summary>" in html
    assert '<caption class="sr-only">Filterable tagging evidence records</caption>' in html
    assert 'scope="col"' in html
    assert "No records match these filters" in html


def test_dashboard_retry_pdf_controls_and_persistent_selection():
    builder = load_builder()
    html = builder.build_current_dashboard_html()

    assert 'id="recommendSelection"' in html
    assert 'id="selectVisible"' in html
    assert 'id="clearSelection"' in html
    assert 'id="includeHoldouts"' in html
    assert 'id="includeCompleted"' in html
    assert 'id="retryStatusFilter"' in html
    assert 'id="retryLimit"' in html
    assert 'id="generateRetryPdf"' in html
    assert "const selectedFiles = new Set()" in html
    assert "recommendRecords(filteredRecords(), retryLimit())" in html
    assert "fetch('/api/retry-pdf'" in html
    assert "fetch('/api/retry-statuses')" in html
    assert "['결과 입력', result.result_entry_url]" in html
    assert "retryTier(record)" in html
    assert 'className = \'row-selector\'' in html


def test_dashboard_frequency_after_v1_corrections():
    records = load_records()
    active = [record for record in records if record["use_for_tag_frequency"] is True]
    counts = Counter(record["provisional_tags"]["primary"] for record in active)

    assert counts["SCOPE_CONDITION_MISAPPLICATION"] == 18
    assert counts["CONCEPT_LAYER_CONFUSION"] == 14
    assert counts["TABLE_DIAGRAM_ENCODING_ERROR"] == 10
    assert counts["RELATION_DIRECTION_REVERSAL"] == 4
    assert counts["TEXTUAL_REDEFINITION_MISSED"] == 3
    assert counts["FORMAL_CONDITION_ERROR"] == 10
    assert counts["GLOBAL_CONSTRAINT_DROPPED"] == 10
    assert counts["UNWARRANTED_ASSUMPTION_ADDED"] == 6
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


def test_retry_pdf_payload_validates_allowlisted_review_files():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    records = load_records()
    active = next(record for record in records if not record["holdout"])
    result = serve_tagging_dashboard.validate_retry_pdf_payload(
        {
            "review_files": [active["review_file"], active["review_file"]],
            "limit": 20,
            "include_holdout": False,
            "title": "Focused retry",
        }
    )

    assert result["review_files"] == [active["review_file"]]
    assert result["limit"] == 20
    assert result["include_completed"] is False

    with pytest.raises(ValueError, match="Unknown review_file"):
        serve_tagging_dashboard.validate_retry_pdf_payload(
            {"review_files": ["data/reviews/not-in-dashboard.review.json"]}
        )
    with pytest.raises(ValueError, match="Unknown fields"):
        serve_tagging_dashboard.validate_retry_pdf_payload({"output_path": "../escape.pdf"})


def test_retry_pdf_payload_requires_explicit_holdout_opt_in(monkeypatch):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    holdout = dict(load_records()[0])
    holdout["review_file"] = "data/reviews/synthetic-holdout/q01.review.json"
    holdout["holdout"] = True
    holdout["use_for_tag_frequency"] = False
    holdout["use_for_final_tag_promotion"] = False
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "load_records", lambda: [holdout])
    with pytest.raises(ValueError, match="include_holdout=true"):
        serve_tagging_dashboard.validate_retry_pdf_payload(
            {"review_files": [holdout["review_file"]], "include_holdout": False}
        )

    result = serve_tagging_dashboard.validate_retry_pdf_payload(
        {"review_files": [holdout["review_file"]], "include_holdout": True}
    )
    assert result["review_files"] == [holdout["review_file"]]


def test_retry_pdf_response_calls_shared_generator(monkeypatch):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    active = next(record for record in load_records() if not record["holdout"])
    captured = {}

    class FakeRetryPdfError(Exception):
        pass

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            session_id="retry-test-session",
            pdf_path=Path("output/retry-pdfs/example.pdf"),
            manifest_path=Path("output/retry-pdfs/example.json"),
            selected=[{"review_file": active["review_file"]}],
            skipped=[],
        )

    monkeypatch.setattr(
        serve_tagging_dashboard,
        "_load_retry_pdf_api",
        lambda: (fake_create, FakeRetryPdfError),
    )
    monkeypatch.setattr(
        serve_tagging_dashboard,
        "_output_reference",
        lambda path: (Path(path).as_posix(), f"/download?file={Path(path).name}"),
    )

    response = serve_tagging_dashboard.create_retry_pdf_response(
        {"review_files": [active["review_file"]], "title": "Focused retry"}
    )

    assert captured["data_root"] == ROOT / "data"
    assert captured["review_files"] == [active["review_file"]]
    assert captured["output_path"].is_relative_to(ROOT / "output")
    assert captured["output_path"].suffix == ".pdf"
    assert captured["font_path"] is None
    assert captured["include_completed"] is False
    assert response["selected_count"] == 1
    assert response["session_id"] == "retry-test-session"
    assert response["pdf_url"].startswith("/download?")
    assert response["result_entry_url"].startswith("/retry-results?manifest=")
    assert "selected" not in response


def test_retry_result_payload_rejects_answer_key_claims_and_normalizes_answers(monkeypatch):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    manifest = ROOT / "output" / "pdf" / "retry-pdfs" / "session.json"
    monkeypatch.setattr(
        serve_tagging_dashboard,
        "resolve_retry_manifest",
        lambda value, must_exist: manifest,
    )
    result = serve_tagging_dashboard.validate_retry_result_payload(
        {
            "manifest_path": "output/pdf/retry-pdfs/session.json",
            "answers": [
                {
                    "review_file": "data\\reviews\\exam\\q01.review.json",
                    "selected_choice": 3,
                    "note": "  다시 검산  ",
                }
            ],
        }
    )
    assert result == {
        "manifest_path": manifest,
        "answers": [
            {
                "review_file": "data/reviews/exam/q01.review.json",
                "selected_choice": 3,
                "note": "다시 검산",
            }
        ],
    }
    with pytest.raises(ValueError, match="Unknown answer fields"):
        serve_tagging_dashboard.validate_retry_result_payload(
            {
                "manifest_path": "session.json",
                "answers": [
                    {
                        "review_file": "data/reviews/exam/q01.review.json",
                        "selected_choice": 3,
                        "correct_choice": 3,
                    }
                ],
            }
        )


def test_retry_status_response_serializes_statuses(monkeypatch):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    status = SimpleNamespace(review_file="data/reviews/exam/q01.review.json")
    monkeypatch.setattr(
        serve_tagging_dashboard,
        "_load_retry_result_api",
        lambda: {
            "load_statuses": lambda **kwargs: {status.review_file: status},
            "status_payload": lambda value: {
                "review_file": value.review_file,
                "latest_outcome": "correct",
                "attempt_count": 2,
            },
        },
    )

    response = serve_tagging_dashboard.retry_status_response()

    assert response["by_review_file"][status.review_file]["latest_outcome"] == "correct"


def test_retry_results_page_hides_answer_until_a_result_exists(monkeypatch, tmp_path):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    manifest_path = tmp_path / "session.json"
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)
    monkeypatch.setattr(
        serve_tagging_dashboard,
        "resolve_retry_manifest",
        lambda value, must_exist: manifest_path,
    )
    monkeypatch.setattr(
        serve_tagging_dashboard,
        "_load_retry_result_api",
        lambda: {
            "load_manifest": lambda path: {
                "session_id": "retry-session",
                "title": "집중력 재점검",
                "selected": [
                    {
                        "review_file": "data/reviews/exam/q01.review.json",
                        "year": 2025,
                        "section": "언어이해",
                        "question_no": 1,
                        "correct_choice": 4,
                    }
                ],
            },
            "result_path": lambda *args, **kwargs: tmp_path / "missing-result.json",
            "load_result": lambda path: None,
        },
    )

    html = serve_tagging_dashboard.build_retry_results_page("session.json")

    assert "재풀이 결과 입력" in html
    assert "data/reviews/exam/q01.review.json" in html
    assert "정답 4" not in html
    assert "fetch('/api/retry-results'" in html


def test_retry_pdf_download_rejects_paths_outside_output():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    with pytest.raises(ValueError, match="output directory"):
        serve_tagging_dashboard.resolve_output_file("README.md", must_exist=False)
    with pytest.raises(ValueError, match="PDF and JSON"):
        serve_tagging_dashboard.resolve_output_file("output/retry-pdfs/notes.txt", must_exist=False)
