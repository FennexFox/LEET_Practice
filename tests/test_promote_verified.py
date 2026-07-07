from __future__ import annotations

import json
from pathlib import Path

import pytest

from leet_practice.verification import (
    VerificationError,
    VerifiedQuestionDraft,
    initialize_review_state,
    promote_verified,
    update_candidate,
    validate_promotion,
)
from leet_practice.models import Choice


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


def _verified_question(
    *,
    stem: str = "Verified question",
    correct_answer: int = 2,
    correct_choice: int = 2,
) -> VerifiedQuestionDraft:
    return VerifiedQuestionDraft(
        id="leet-2026-verbal-even-q001",
        exam_id="leet-2026-verbal-even",
        question_no=1,
        stem=stem,
        choices=[
            Choice(choice_no=index, text=f"Choice {index}", is_correct=index == correct_choice)
            for index in range(1, 6)
        ],
        correct_answer=correct_answer,
        source_provenance={"original": {"suggestion_id": "q01"}},
    )


def test_validate_promotion_rejects_answer_flag_mismatch() -> None:
    question = _verified_question(correct_answer=2, correct_choice=1)

    with pytest.raises(VerificationError, match="correct_answer=2.*is_correct flags: \\[1\\]"):
        validate_promotion([], [question])


def test_validate_promotion_rejects_collapsed_korean_spacing() -> None:
    collapsed = "다음글을읽고옳은것만을보기에서있는대로고른것은" * 2
    question = _verified_question(stem=collapsed)

    with pytest.raises(VerificationError, match="collapsed Korean spacing"):
        validate_promotion([], [question])
