from __future__ import annotations

import json
from pathlib import Path

from leet_practice.verification import (
    ReviewStatus,
    initialize_review_state,
    load_review_state,
    passage_drafts_path,
    question_drafts_path,
    review_state_path,
    update_candidate,
)


def make_suggestion_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "artifacts" / "question_crop_suggestions" / "run"
    (run_dir / "q01_candidate").mkdir(parents=True)
    (run_dir / "set_01_03_passage_candidate").mkdir(parents=True)
    (run_dir / "q01_candidate" / "q01_candidate_preview.png").write_bytes(b"preview")
    (run_dir / "set_01_03_passage_candidate" / "set_01_03_passage_candidate_preview.png").write_bytes(b"preview")
    (run_dir / "page_001_left.paddleocr.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"row_index": 0, "text": "passage line"},
                    {"row_index": 1, "text": "question line"},
                ]
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "artifact_type": "candidate_question_crop_suggestions",
        "suggestions": [
            {
                "suggestion_id": "set_01_03_passage",
                "kind": "candidate_passage_crop_suggestion",
                "start_question": 1,
                "end_question": 3,
                "candidate_preview_path": "set_01_03_passage_candidate/set_01_03_passage_candidate_preview.png",
                "parts": [
                    {
                        "page": 1,
                        "column": "left",
                        "block_id": "p001_left",
                        "included_row_ids": ["p001_left_r000"],
                    }
                ],
            },
            {
                "suggestion_id": "q01",
                "kind": "candidate_question_crop_suggestion",
                "question_number": 1,
                "set_start_question": 1,
                "set_end_question": 3,
                "candidate_preview_path": "q01_candidate/q01_candidate_preview.png",
                "parts": [
                    {
                        "page": 1,
                        "column": "left",
                        "block_id": "p001_left",
                        "included_row_ids": ["p001_left_r001"],
                    }
                ],
            },
        ],
    }
    suggestions_path = run_dir / "suggestions.json"
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")
    return suggestions_path


def test_initialize_review_state_preserves_queue_and_ocr_text(tmp_path: Path) -> None:
    suggestions_path = make_suggestion_run(tmp_path)
    data_root = tmp_path / "data"

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)

    assert review_state_path("leet-2026-verbal-even", data_root=data_root).exists()
    assert [candidate.status for candidate in state.candidates] == [ReviewStatus.UNREVIEWED, ReviewStatus.UNREVIEWED]
    assert state.candidates[0].raw_ocr_text == "passage line"
    assert state.candidates[1].raw_ocr_text == "question line"
    assert state.candidates[1].passage_id == "leet-2026-verbal-even-passage-001-003"


def test_update_candidate_writes_accepted_drafts(tmp_path: Path) -> None:
    suggestions_path = make_suggestion_run(tmp_path)
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
