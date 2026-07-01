from __future__ import annotations

import json
from pathlib import Path

import pytest

from leet_practice.verification import (
    VerificationError,
    initialize_review_state,
    promote_verified,
    update_candidate,
)


def _accept_sample_drafts(data_root: Path, suggestions_path: Path) -> None:
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


def test_promote_verified_writes_canonical_files(tmp_path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    _accept_sample_drafts(data_root, suggestions_path)

    passage_path, question_path, passage_count, question_count = promote_verified(
        "leet-2026-verbal-even",
        data_root=data_root,
    )

    assert passage_count == 1
    assert question_count == 1
    assert json.loads(passage_path.read_text(encoding="utf-8").splitlines()[0])["body_text"] == "Verified passage"
    question = json.loads(question_path.read_text(encoding="utf-8").splitlines()[0])
    assert question["stem"] == "Verified question"
    assert question["source_provenance"]["original"]["suggestion_id"] == "q01"


def test_promote_verified_creates_backup_before_overwriting_canonical_files(tmp_path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    _accept_sample_drafts(data_root, suggestions_path)
    passage_path, question_path, _, _ = promote_verified("leet-2026-verbal-even", data_root=data_root)
    passage_path.write_text("old passages\n", encoding="utf-8")
    question_path.write_text("old questions\n", encoding="utf-8")

    promote_verified("leet-2026-verbal-even", data_root=data_root)

    assert passage_path.with_name("passages.jsonl.bak").read_text(encoding="utf-8") == "old passages\n"
    assert question_path.with_name("questions.jsonl.bak").read_text(encoding="utf-8") == "old questions\n"


def test_promote_verified_fails_before_writing_invalid_question(tmp_path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)
    update_candidate(
        "leet-2026-verbal-even",
        "q01",
        {
            "status": "accepted",
            "stem": "Verified question",
            "choices": ["A", "", "C", "D", "E"],
            "correct_answer": 2,
        },
        data_root=data_root,
    )

    with pytest.raises(VerificationError, match="empty choice"):
        promote_verified("leet-2026-verbal-even", data_root=data_root)

    assert not (data_root / "canonical" / "leet-2026-verbal-even" / "questions.jsonl").exists()
