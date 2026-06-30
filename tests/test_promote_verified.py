from __future__ import annotations

import json

import pytest

from leet_practice.verification import (
    VerificationError,
    initialize_review_state,
    promote_verified,
    update_candidate,
)
from tests.test_verification_storage import make_suggestion_run


def test_promote_verified_writes_canonical_files(tmp_path) -> None:
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


def test_promote_verified_fails_before_writing_invalid_question(tmp_path) -> None:
    suggestions_path = make_suggestion_run(tmp_path)
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
