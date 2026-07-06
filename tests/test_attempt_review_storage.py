from __future__ import annotations

import json
from pathlib import Path

import pytest

from leet_practice.attempt_review import (
    AttemptReviewError,
    create_attempt_record,
    export_feedback_bundle,
    import_assistant_feedback,
    initialize_attempt_reviews,
    load_answer_key,
    load_review_record,
    review_path,
    update_user_self_review,
)
from leet_practice.models import AttemptReviewStatus


def _write_answer_key(data_root: Path, exam_id: str, answers: dict[int, int]) -> None:
    path = data_root / "canonical" / exam_id / "answer_key.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"answers": {str(key): value for key, value in answers.items()}}), encoding="utf-8")


def _write_questions_jsonl(data_root: Path, exam_id: str, answers: dict[int, int]) -> None:
    path = data_root / "canonical" / exam_id / "questions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": f"{exam_id}-q{question_no:03d}",
            "exam_id": exam_id,
            "question_no": question_no,
            "stem": f"Question {question_no}",
            "choices": [{"choice_no": index, "text": f"Choice {index}"} for index in range(1, 6)],
            "correct_answer": answer,
        }
        for question_no, answer in sorted(answers.items())
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_load_answer_key_prefers_answer_key_json(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 2, 2: 4})
    _write_questions_jsonl(data_root, exam_id, {1: 2, 2: 4})

    answer_key = load_answer_key(exam_id, data_root=data_root)

    assert answer_key.answers == {1: 2, 2: 4}
    assert answer_key.source.endswith("answer_key.json")


def test_load_answer_key_uses_questions_jsonl_fallback(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_questions_jsonl(data_root, exam_id, {1: 2, 2: 4})

    answer_key = load_answer_key(exam_id, data_root=data_root)

    assert answer_key.answers == {1: 2, 2: 4}
    assert answer_key.source.endswith("questions.jsonl")


def test_load_answer_key_errors_when_sources_disagree(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 2})
    _write_questions_jsonl(data_root, exam_id, {1: 3})

    with pytest.raises(AttemptReviewError, match="disagree"):
        load_answer_key(exam_id, data_root=data_root)


def test_initialize_attempt_reviews_writes_wrong_question_review_files(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 1, 2: 4, 3: 5})
    _write_questions_jsonl(data_root, exam_id, {1: 1, 2: 4, 3: 5})
    create_attempt_record("attempt-001", exam_id, "125", data_root=data_root)

    state = initialize_attempt_reviews("attempt-001", data_root=data_root)

    assert state.score == 2
    assert state.wrong_question_numbers == [2]
    assert [review.question_no for review in state.reviews] == [2]
    assert review_path("attempt-001", 2, data_root=data_root).exists()
    assert not review_path("attempt-001", 1, data_root=data_root).exists()


def test_create_real_attempt_requires_full_answer_count(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 1, 2: 4, 3: 5})

    with pytest.raises(AttemptReviewError, match="Real-mode attempt"):
        create_attempt_record("attempt-001", exam_id, "14", data_root=data_root)


def test_create_partial_attempt_allows_short_answer_count(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 1, 2: 4, 3: 5})

    attempt = create_attempt_record("attempt-001", exam_id, "14", data_root=data_root, mode="partial")

    assert [answer.question_no for answer in attempt.answers] == [1, 2]


def test_assistant_feedback_import_preserves_user_self_review(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    update_user_self_review(
        "attempt-001",
        1,
        {"why_selected": "I matched the wrong condition.", "status": "ready_for_feedback"},
        data_root=data_root,
    )
    feedback_file = tmp_path / "assistant_feedback.json"
    feedback_file.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "question_no": 1,
                        "assistant_feedback": {
                            "diagnosis_text": "Condition reversal.",
                            "evidence": ["selected answer ignores the final condition"],
                            "provisional_error_tags": ["condition_reversal"],
                            "correction_rule": "Check necessary and sufficient directions.",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    import_assistant_feedback("attempt-001", feedback_file, data_root=data_root)

    review = load_review_record("attempt-001", 1, data_root=data_root)
    assert review.user_self_review.why_selected == "I matched the wrong condition."
    assert review.assistant_feedback is not None
    assert review.assistant_feedback.provisional_error_tags == ["condition_reversal"]
    assert review.status == AttemptReviewStatus.FEEDBACK_ADDED


def test_user_self_review_rejects_feedback_status(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)

    with pytest.raises(AttemptReviewError, match="Self-review status"):
        update_user_self_review(
            "attempt-001",
            1,
            {"why_selected": "Surface match.", "status": "feedback_added"},
            data_root=data_root,
        )


def test_export_feedback_bundle_contains_user_review_not_resolution(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    _write_questions_jsonl(data_root, exam_id, {1: 3})
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    update_user_self_review(
        "attempt-001",
        1,
        {"reasoning_text": "I chose by surface similarity.", "status": "ready_for_feedback"},
        data_root=data_root,
    )

    out_path = export_feedback_bundle("attempt-001", data_root=data_root)
    bundle = json.loads(out_path.read_text(encoding="utf-8"))

    assert bundle["artifact_type"] == "leet_practice_attempt_review_feedback_request"
    assert bundle["reviews"][0]["user_self_review"]["reasoning_text"] == "I chose by surface similarity."
    assert "user_resolution" not in bundle["reviews"][0]
