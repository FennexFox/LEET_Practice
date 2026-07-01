from __future__ import annotations

import json
from pathlib import Path

import pytest

from leet_practice.verification import (
    ReviewStatus,
    VerificationError,
    initialize_review_state,
    load_review_state,
    passage_drafts_path,
    question_drafts_path,
    review_state_path,
    update_candidate,
)


def test_initialize_review_state_preserves_queue_and_ocr_text(tmp_path: Path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)

    assert review_state_path("leet-2026-verbal-even", data_root=data_root).exists()
    assert [candidate.status for candidate in state.candidates] == [ReviewStatus.UNREVIEWED, ReviewStatus.UNREVIEWED]
    assert state.candidates[0].raw_ocr_text == "passage line"
    assert state.candidates[1].raw_ocr_text == "question line"
    assert state.candidates[1].passage_id == "leet-2026-verbal-even-passage-001-003"


def test_update_candidate_writes_accepted_drafts(tmp_path: Path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)

    update_candidate(
        "leet-2026-verbal-even",
        "set_01_03_passage",
        {"status": "accepted", "verified_text": "Verified passage"},
        data_root=data_root,
    )
    update_candidate(
        "leet-2026-verbal-even",
        "q01",
        {
            "status": "accepted",
            "stem": "Verified question",
            "choices": ["A", "B", "C", "D", "E"],
            "correct_answer": 2,
        },
        data_root=data_root,
    )

    state = load_review_state("leet-2026-verbal-even", data_root=data_root)
    assert [candidate.status for candidate in state.candidates] == [ReviewStatus.ACCEPTED, ReviewStatus.ACCEPTED]
    passage_rows = passage_drafts_path("leet-2026-verbal-even", data_root=data_root).read_text(encoding="utf-8").splitlines()
    question_rows = question_drafts_path("leet-2026-verbal-even", data_root=data_root).read_text(encoding="utf-8").splitlines()
    assert len(passage_rows) == 1
    assert len(question_rows) == 1
    assert json.loads(question_rows[0])["source_provenance"]["original"]["suggestion_id"] == "q01"


def test_parse_suggestions_rejects_duplicate_candidate_ids(tmp_path: Path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    duplicate = dict(payload["suggestions"][1])
    duplicate["suggestion_id"] = "q01!"
    payload["suggestions"].append(duplicate)
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VerificationError, match="Duplicate candidate_id"):
        initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")


def test_parse_suggestions_rejects_preview_paths_outside_run(tmp_path: Path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    payload["suggestions"][1]["candidate_preview_path"] = "../outside.png"
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VerificationError, match="escapes suggestions directory"):
        initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")


def test_parse_suggestions_accepts_repo_relative_preview_paths(
    tmp_path: Path,
    suggestion_run: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suggestions_path = suggestion_run
    payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    run_relative = Path("artifacts") / "question_crop_suggestions" / "run"
    payload["suggestions"][0]["candidate_preview_path"] = str(
        run_relative / "set_01_03_passage_candidate" / "set_01_03_passage_candidate_preview.png"
    )
    payload["suggestions"][1]["candidate_preview_path"] = str(run_relative / "q01_candidate" / "q01_candidate_preview.png")
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")

    assert Path(state.candidates[0].preview_path or "").exists()
    assert Path(state.candidates[1].preview_path or "").exists()


def test_passage_range_edit_resyncs_linked_question_passage_ids(tmp_path: Path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)

    update_candidate(
        "leet-2026-verbal-even",
        "set_01_03_passage",
        {"start_question": 1, "end_question": 4},
        data_root=data_root,
    )

    state = load_review_state("leet-2026-verbal-even", data_root=data_root)
    question = next(candidate for candidate in state.candidates if candidate.candidate_id == "q01")
    assert question.passage_id == "leet-2026-verbal-even-passage-001-004"


def test_refresh_preserving_edits_keeps_touched_candidates_and_refreshes_untouched(
    tmp_path: Path,
    suggestion_run: Path,
) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)
    update_candidate(
        "leet-2026-verbal-even",
        "set_01_03_passage",
        {"status": "needs_fix", "verified_text": "Manual passage"},
        data_root=data_root,
    )

    payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    ocr_path = suggestions_path.parent / "page_001_left.paddleocr.json"
    ocr_payload = json.loads(ocr_path.read_text(encoding="utf-8"))
    ocr_payload["rows"][0]["text"] = "new passage OCR"
    ocr_payload["rows"][1]["text"] = "1. New question?\n1) A\n2) B\n3) C\n4) D\n5) E"
    ocr_path.write_text(json.dumps(ocr_payload), encoding="utf-8")
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

    state = initialize_review_state(
        "leet-2026-verbal-even",
        suggestions_path,
        data_root=data_root,
        refresh_preserving_edits=True,
    )

    passage = next(candidate for candidate in state.candidates if candidate.candidate_id == "set_01_03_passage")
    question = next(candidate for candidate in state.candidates if candidate.candidate_id == "q01")
    assert passage.raw_ocr_text == "new passage OCR"
    assert passage.verified_text == "Manual passage"
    assert passage.status == ReviewStatus.NEEDS_FIX
    assert passage.manually_edited is True
    assert question.raw_ocr_text == "1. New question?\n1) A\n2) B\n3) C\n4) D\n5) E"
    assert question.stem == "New question?"
    assert question.choices == ["A", "B", "C", "D", "E"]
    assert question.manually_edited is False
