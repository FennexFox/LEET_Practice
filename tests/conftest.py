from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest


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


@pytest.fixture
def suggestion_run(tmp_path: Path) -> Path:
    return make_suggestion_run(tmp_path)


@pytest.fixture
def suggestion_run_factory(tmp_path: Path) -> Callable[[], Path]:
    return lambda: make_suggestion_run(tmp_path)
