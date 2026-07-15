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

    assert len(records) == 112
    assert all(
        isinstance(record.get("review_input_at"), str) and record["review_input_at"]
        for record in records
    )
    assert sum(record["use_for_tag_frequency"] is True for record in records) == 112
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


def test_2024_reviews_are_fully_tagged():
    records = [record for record in load_records() if record["year"] == 2024]

    assert len(records) == 17
    assert {(record["section"], record["question_no"]) for record in records} == {
        ("언어이해", 1),
        ("언어이해", 3),
        ("언어이해", 7),
        ("언어이해", 12),
        ("언어이해", 15),
        ("언어이해", 18),
        ("언어이해", 19),
        ("언어이해", 21),
        ("언어이해", 28),
        ("추리논증", 4),
        ("추리논증", 8),
        ("추리논증", 12),
        ("추리논증", 13),
        ("추리논증", 15),
        ("추리논증", 16),
        ("추리논증", 27),
        ("추리논증", 37),
    }
    assert all(record["provisional_tags"]["confidence"] == "high" for record in records)
    assert all(record["needs_review"] is False for record in records)
    assert all(record["holdout"] is False for record in records)


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
    assert 'id="retrySessionLookup"' in html
    assert 'id="retrySessionCode"' in html
    assert 'id="deleteSessionById"' in html
    assert 'id="recentRetrySessions"' in html
    assert "const selectedFiles = new Set()" in html
    assert "recommendRecords(filteredRecords(), retryLimit())" in html
    assert "function reviewInputTimestamp(record)" in html
    assert "record.review_input_at" in html
    assert "recommendation.sort(compareRetryRecords)" in html
    assert "fetch('/api/retry-pdf'" in html
    assert "fetch('/api/retry-statuses')" in html
    assert "fetch('/api/retry-sessions')" in html
    assert "method: 'DELETE'" in html
    assert "confirm_session_id: session.session_id" in html
    assert "['결과 입력', result.result_entry_url]" in html
    assert "/retry-results?session=${encodeURIComponent(session)}" in html
    assert "loadRecentRetrySessions();" in html
    assert "retryTier(record)" in html
    assert 'className = \'row-selector\'' in html


def test_dashboard_retry_session_lookup_is_accessible_and_server_explicit():
    builder = load_builder()
    html = builder.build_current_dashboard_html()

    assert '<h3 id="retryHistoryTitle">기존 재풀이 세션 관리</h3>' in html
    assert '<label class="retry-session-field" for="retrySessionCode">' in html
    assert 'aria-describedby="retrySessionLookupHint"' in html
    assert 'id="retrySessionHistoryStatus"' in html
    assert 'role="status" aria-live="polite"' in html
    assert 'tabindex="-1"' in html
    assert 'python tools/serve_tagging_dashboard.py' in html
    assert "window.location.protocol === 'file:'" in html
    assert "결과 입력은 로컬 대시보드 서버에서 열어 주세요." in html
    assert "textContent = session.title" in html
    assert 'id="retrySessionDeleteHint"' in html
    assert "PDF, 매니페스트와 저장된 풀이 결과가 함께 삭제" in html
    assert "window.confirm(" in html
    assert "`세션 ID: ${session.session_id}`" in html
    assert "deleteButton.type = 'button'" in html
    assert "deleteButton.className = 'retry-session-delete'" in html
    assert "${session.title || '재풀이'} ${session.session_id} 재풀이 세션 삭제" in html
    assert "deleteButton.setAttribute('aria-describedby', 'retrySessionDeleteHint')" in html
    assert "item.setAttribute('aria-busy', 'true')" in html
    assert "deleteRetrySession(session, item, deleteButton)" in html
    assert "await loadRecentRetrySessions(" in html
    assert "await loadRetryStatuses()" in html
    assert "selectedFiles.has(record.review_file) && !isRetryEligible(record)" in html
    assert "retryStatusesLoaded = false" in html
    assert "if (!retryStatusesLoaded && !includeCompleted) return false" in html
    assert "data.records.forEach(record => { record.retry_status = null; })" in html
    assert "statusFilter.value = ''" in html
    assert "document.getElementById('retrySessionHistoryStatus').focus()" in html
    assert ".retry-history-status:focus { outline: 2px solid var(--accent)" in html
    assert "{session_id: sessionId, title: '입력한 재풀이 세션'}" in html
    assert "삭제하지 못했습니다:" in html


def test_dashboard_frequency_after_2024_tagging():
    records = load_records()
    active = [record for record in records if record["use_for_tag_frequency"] is True]
    counts = Counter(record["provisional_tags"]["primary"] for record in active)

    assert counts["SCOPE_CONDITION_MISAPPLICATION"] == 22
    assert counts["CONCEPT_LAYER_CONFUSION"] == 20
    assert counts["TABLE_DIAGRAM_ENCODING_ERROR"] == 13
    assert counts["RELATION_DIRECTION_REVERSAL"] == 4
    assert counts["TEXTUAL_REDEFINITION_MISSED"] == 6
    assert counts["FORMAL_CONDITION_ERROR"] == 10
    assert counts["GLOBAL_CONSTRAINT_DROPPED"] == 11
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
    assert "112" in html


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
    assert response["result_entry_url"] == "/retry-results?session=retry-test-session"
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


def _write_retry_manifest(
    path: Path,
    *,
    session_id: str,
    generated_at: str,
    title: str = "Focused retry",
    question_no: int = 1,
    correct_choice: int = 4,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_id": session_id,
                "generated_at": generated_at,
                "title": title,
                "selected": [
                    {
                        "review_file": f"data/reviews/exam/q{question_no:02d}.review.json",
                        "question_id": f"exam-q{question_no:02d}",
                        "year": 2025,
                        "section": "추리논증",
                        "question_no": question_no,
                        "correct_choice": correct_choice,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_retry_session_discovery_returns_private_data_free_recent_summaries(monkeypatch, tmp_path):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    retry_root = tmp_path / "output" / "pdf" / "retry-pdfs"
    older_id = "retry-20260713T120000Z-1111111111"
    newer_id = "retry-20260713T130000Z-2222222222"
    older_path = retry_root / "older.json"
    newer_path = retry_root / "newer.json"
    _write_retry_manifest(
        older_path,
        session_id=older_id,
        generated_at="2026-07-13T12:00:00+00:00",
    )
    _write_retry_manifest(
        newer_path,
        session_id=newer_id,
        generated_at="2026-07-13T13:00:00+00:00",
        title="Newest retry",
        question_no=2,
        correct_choice=3,
    )
    (retry_root / "broken.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)

    api = serve_tagging_dashboard._load_retry_result_api()
    api["save"](
        newer_path,
        [
            {
                "review_file": "data/reviews/exam/q02.review.json",
                "selected_choice": 3,
            }
        ],
        data_root=tmp_path / "data",
    )

    response = serve_tagging_dashboard.retry_sessions_response()

    assert response["count"] == 2
    assert [item["session_id"] for item in response["sessions"]] == [newer_id, older_id]
    newest = response["sessions"][0]
    assert newest["short_code"] == "2222222222"
    assert newest["result_status"] == "submitted"
    assert newest["answered_count"] == 1
    assert newest["correct_count"] == 1
    assert newest["result_entry_url"] == f"/retry-results?session={newer_id}"
    assert "selected" not in newest
    assert "correct_choice" not in newest
    assert "manifest_path" not in newest


def test_retry_session_resolution_supports_full_id_and_unique_short_code(monkeypatch, tmp_path):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    retry_root = tmp_path / "retry-pdfs"
    first = retry_root / "first.json"
    second = retry_root / "second.json"
    first_id = "retry-20260713T120000Z-abcdef1234"
    second_id = "retry-20260713T130000Z-9999999999"
    _write_retry_manifest(
        first,
        session_id=first_id,
        generated_at="2026-07-13T12:00:00+00:00",
    )
    _write_retry_manifest(
        second,
        session_id=second_id,
        generated_at="2026-07-13T13:00:00+00:00",
        question_no=2,
    )
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)

    assert serve_tagging_dashboard.resolve_retry_session_manifest(first_id) == first
    assert serve_tagging_dashboard.resolve_retry_session_manifest("ABCDEF1234") == first
    with pytest.raises(FileNotFoundError, match="not found"):
        serve_tagging_dashboard.resolve_retry_session_manifest("0000000000")
    with pytest.raises(FileNotFoundError, match="not found"):
        serve_tagging_dashboard.resolve_retry_session_manifest("too-short")
    with pytest.raises(ValueError, match="full session ID"):
        serve_tagging_dashboard.resolve_retry_session_manifest("../escape")

    duplicate = retry_root / "duplicate.json"
    _write_retry_manifest(
        duplicate,
        session_id="retry-20260713T140000Z-abcdef1234",
        generated_at="2026-07-13T14:00:00+00:00",
        question_no=3,
    )
    with pytest.raises(ValueError, match="ambiguous"):
        serve_tagging_dashboard.resolve_retry_session_manifest("abcdef1234")


def test_delete_retry_session_removes_manifest_pdf_and_saved_result(monkeypatch, tmp_path):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    retry_root = tmp_path / "output" / "pdf" / "retry-pdfs"
    session_id = "retry-20260713T150000Z-1234567890"
    manifest_path = retry_root / "delete-me.json"
    pdf_path = manifest_path.with_suffix(".pdf")
    _write_retry_manifest(
        manifest_path,
        session_id=session_id,
        generated_at="2026-07-13T15:00:00+00:00",
    )
    pdf_path.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)

    api = serve_tagging_dashboard._load_retry_result_api()
    result_path = api["result_path"](session_id, data_root=tmp_path / "data")
    api["save"](
        manifest_path,
        [
            {
                "review_file": "data/reviews/exam/q01.review.json",
                "selected_choice": 4,
            }
        ],
        data_root=tmp_path / "data",
    )

    payload = {"session_id": session_id, "confirm_session_id": session_id}
    response = serve_tagging_dashboard.delete_retry_session_response(payload)

    assert response == {
        "session_id": session_id,
        "deleted": True,
        "deleted_files": ["manifest", "pdf", "result"],
        "missing_files": [],
        "cleanup_pending": [],
    }
    assert not manifest_path.exists()
    assert not pdf_path.exists()
    assert not result_path.exists()
    assert serve_tagging_dashboard.retry_sessions_response()["count"] == 0
    assert serve_tagging_dashboard.retry_status_response()["by_review_file"] == {}
    with pytest.raises(FileNotFoundError, match="not found"):
        serve_tagging_dashboard.delete_retry_session_response(payload)


def test_delete_retry_session_requires_exact_confirmed_id_and_allows_missing_companions(
    monkeypatch,
    tmp_path,
):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    retry_root = tmp_path / "retry-pdfs"
    session_id = "retry-20260713T160000Z-abcdef1234"
    manifest_path = retry_root / "manifest-only.json"
    _write_retry_manifest(
        manifest_path,
        session_id=session_id,
        generated_at="2026-07-13T16:00:00+00:00",
    )
    outside_pdf = tmp_path / "must-not-delete.pdf"
    outside_pdf.write_bytes(b"outside retry root")
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["pdf_path"] = str(outside_pdf)
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="confirmation"):
        serve_tagging_dashboard.delete_retry_session_response(
            {"session_id": session_id, "confirm_session_id": "wrong-id"}
        )
    with pytest.raises(ValueError, match="full session ID"):
        serve_tagging_dashboard.delete_retry_session_response(
            {"session_id": "abcdef1234", "confirm_session_id": "abcdef1234"}
        )
    with pytest.raises(ValueError, match="valid full session ID"):
        serve_tagging_dashboard.delete_retry_session_response(
            {"session_id": "../escape", "confirm_session_id": "../escape"}
        )
    with pytest.raises(ValueError, match="Unknown fields"):
        serve_tagging_dashboard.delete_retry_session_response(
            {
                "session_id": session_id,
                "confirm_session_id": session_id,
                "manifest_path": str(manifest_path),
            }
        )
    assert manifest_path.is_file()

    response = serve_tagging_dashboard.delete_retry_session_response(
        {"session_id": session_id, "confirm_session_id": session_id}
    )

    assert response["deleted"] is True
    assert response["deleted_files"] == ["manifest"]
    assert response["missing_files"] == ["pdf", "result"]
    assert not manifest_path.exists()
    assert outside_pdf.is_file()


def test_delete_retry_session_rejects_duplicate_full_ids(monkeypatch, tmp_path):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    retry_root = tmp_path / "retry-pdfs"
    session_id = "retry-20260713T170000Z-1111111111"
    first = retry_root / "first.json"
    second = retry_root / "second.json"
    _write_retry_manifest(
        first,
        session_id=session_id,
        generated_at="2026-07-13T17:00:00+00:00",
    )
    _write_retry_manifest(
        second,
        session_id=session_id,
        generated_at="2026-07-13T17:01:00+00:00",
        question_no=2,
    )
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="Multiple manifests"):
        serve_tagging_dashboard.delete_retry_session_response(
            {"session_id": session_id, "confirm_session_id": session_id}
        )

    assert first.is_file()
    assert second.is_file()


def test_delete_retry_session_restores_staged_files_when_preparation_fails(
    monkeypatch,
    tmp_path,
):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    retry_root = tmp_path / "retry-pdfs"
    session_id = "retry-20260713T180000Z-2222222222"
    manifest_path = retry_root / "rollback.json"
    pdf_path = manifest_path.with_suffix(".pdf")
    _write_retry_manifest(
        manifest_path,
        session_id=session_id,
        generated_at="2026-07-13T18:00:00+00:00",
    )
    pdf_path.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)
    api = serve_tagging_dashboard._load_retry_result_api()
    result_path = api["result_path"](session_id, data_root=tmp_path / "data")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text("{}", encoding="utf-8")

    real_replace = Path.replace

    def fail_for_pdf(path, target):
        if path == pdf_path:
            raise OSError("synthetic open PDF")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_for_pdf)
    with pytest.raises(serve_tagging_dashboard.RetrySessionDeleteConflict, match="Close the PDF"):
        serve_tagging_dashboard.delete_retry_session_response(
            {"session_id": session_id, "confirm_session_id": session_id}
        )

    assert manifest_path.is_file()
    assert pdf_path.is_file()
    assert result_path.is_file()
    assert not list(tmp_path.rglob("*.deleting"))


def test_delete_retry_session_reports_tombstone_cleanup_pending(monkeypatch, tmp_path):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import serve_tagging_dashboard

    retry_root = tmp_path / "retry-pdfs"
    session_id = "retry-20260713T190000Z-3333333333"
    manifest_path = retry_root / "cleanup.json"
    pdf_path = manifest_path.with_suffix(".pdf")
    _write_retry_manifest(
        manifest_path,
        session_id=session_id,
        generated_at="2026-07-13T19:00:00+00:00",
    )
    pdf_path.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)
    real_unlink = Path.unlink

    def fail_for_pdf_tombstone(path, missing_ok=False):
        if ".pdf." in path.name and path.name.endswith(".deleting"):
            raise OSError("synthetic cleanup failure")
        return real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_for_pdf_tombstone)
    response = serve_tagging_dashboard.delete_retry_session_response(
        {"session_id": session_id, "confirm_session_id": session_id}
    )

    assert response["deleted"] is True
    assert response["cleanup_pending"] == ["pdf"]
    assert not manifest_path.exists()
    assert not pdf_path.exists()
    assert serve_tagging_dashboard.retry_sessions_response()["count"] == 0
    assert len(list(retry_root.glob("*.deleting"))) == 1


def test_retry_session_delete_http_endpoint_maps_validation_and_conflicts(monkeypatch, tmp_path):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import http.client
    import threading

    import serve_tagging_dashboard

    retry_root = tmp_path / "retry-pdfs"
    session_id = "retry-20260713T210000Z-5555555555"
    manifest_path = retry_root / "http-delete.json"
    pdf_path = manifest_path.with_suffix(".pdf")
    _write_retry_manifest(
        manifest_path,
        session_id=session_id,
        generated_at="2026-07-13T21:00:00+00:00",
    )
    pdf_path.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(serve_tagging_dashboard, "RETRY_OUTPUT_ROOT", retry_root)
    monkeypatch.setattr(serve_tagging_dashboard.dashboard, "ROOT", tmp_path)

    httpd = serve_tagging_dashboard.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        serve_tagging_dashboard.TaggingDashboardHandler,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def delete(payload):
        connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
        try:
            connection.request(
                "DELETE",
                "/api/retry-sessions",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
        finally:
            connection.close()

    try:
        status, _ = delete(
            {"session_id": session_id, "confirm_session_id": "wrong-id"}
        )
        assert status == HTTPStatus.BAD_REQUEST
        assert manifest_path.is_file()

        status, response = delete(
            {"session_id": session_id, "confirm_session_id": session_id}
        )
        assert status == HTTPStatus.OK
        assert response["deleted_files"] == ["manifest", "pdf"]

        status, _ = delete(
            {"session_id": session_id, "confirm_session_id": session_id}
        )
        assert status == HTTPStatus.NOT_FOUND

        conflict_id = "retry-20260713T220000Z-6666666666"
        conflict_manifest = retry_root / "http-conflict.json"
        _write_retry_manifest(
            conflict_manifest,
            session_id=conflict_id,
            generated_at="2026-07-13T22:00:00+00:00",
        )

        def raise_conflict(paths):
            raise serve_tagging_dashboard.RetrySessionDeleteConflict("synthetic conflict")

        monkeypatch.setattr(
            serve_tagging_dashboard,
            "_delete_retry_session_files",
            raise_conflict,
        )
        status, _ = delete(
            {"session_id": conflict_id, "confirm_session_id": conflict_id}
        )
        assert status == HTTPStatus.CONFLICT
        assert conflict_manifest.is_file()
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def test_retry_pdf_download_rejects_paths_outside_output():
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    import pytest
    import serve_tagging_dashboard

    with pytest.raises(ValueError, match="output directory"):
        serve_tagging_dashboard.resolve_output_file("README.md", must_exist=False)
    with pytest.raises(ValueError, match="PDF and JSON"):
        serve_tagging_dashboard.resolve_output_file("output/retry-pdfs/notes.txt", must_exist=False)
