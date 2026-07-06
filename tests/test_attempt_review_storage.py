from __future__ import annotations

import json
from pathlib import Path

import pytest

from leet_practice.attempt_review import (
    AttemptReviewError,
    archived_reviews_dir,
    create_attempt_record,
    export_feedback_bundle,
    import_assistant_feedback,
    initialize_attempt_reviews,
    load_answer_key,
    load_review_record,
    migrate_self_review_files,
    parse_answer_updates,
    regrade_attempt,
    review_path,
    update_user_self_review,
)
from leet_practice.models import AttemptReviewStatus, MemoryConfidence, UserSelfReview


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
            "choices": [
                {"choice_no": index, "text": f"Choice {index}", "is_correct": index == answer}
                for index in range(1, 6)
            ],
            "correct_answer": answer,
        }
        for question_no, answer in sorted(answers.items())
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_passages_jsonl(data_root: Path, exam_id: str) -> None:
    path = data_root / "canonical" / exam_id / "passages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "id": f"{exam_id}-passage-001",
        "exam_id": exam_id,
        "passage_no": 1,
        "question_range": [1, 1],
        "body_text": "Passage text\n\nSecond paragraph",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


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


def test_load_answer_key_validates_matching_question_choice_metadata(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_questions_jsonl(data_root, exam_id, {1: 5})

    answer_key = load_answer_key(exam_id, data_root=data_root)

    assert answer_key.answers == {1: 5}


def test_load_answer_key_errors_when_question_choice_metadata_disagrees(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    path = data_root / "canonical" / exam_id / "questions.jsonl"
    path.parent.mkdir(parents=True)
    row = {
        "id": f"{exam_id}-q03",
        "exam_id": exam_id,
        "question_no": 3,
        "stem": "Question 3",
        "choices": [
            {"choice_no": index, "text": f"Choice {index}", "is_correct": index == 5}
            for index in range(1, 6)
        ],
        "correct_answer": 4,
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(
        AttemptReviewError,
        match=r"exam_id='leet-2026-reasoning-even'.*question_no=3.*correct_answer=4.*correct_choice_from_choices=5",
    ):
        load_answer_key(exam_id, data_root=data_root)


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


def test_user_self_review_defaults_to_simplified_fields() -> None:
    payload = UserSelfReview().model_dump(mode="json")

    assert payload["reasoning_text"] == ""
    assert payload["current_reflection"] == ""
    assert payload["memory_confidence"] == MemoryConfidence.PARTIAL
    assert "why_selected" not in payload
    assert "decisive_condition" not in payload
    assert "why_rejected_correct" not in payload
    assert "condition_notes" not in payload


def test_parse_answer_updates_accepts_repeated_question_choice_pairs() -> None:
    assert parse_answer_updates(["2=4", "12:5"]) == {2: 4, 12: 5}


def test_parse_answer_updates_rejects_duplicate_question() -> None:
    with pytest.raises(AttemptReviewError, match="Duplicate"):
        parse_answer_updates(["2=4", "2=5"])


def test_regrade_updates_selected_answers_and_preserves_user_self_review(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 1, 2: 4, 3: 5})
    create_attempt_record("attempt-001", exam_id, "125", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    update_user_self_review(
        "attempt-001",
        2,
        {
            "reasoning_text": "I entered the wrong selected answer.",
            "current_reflection": "The original answer entry was stale.",
            "memory_confidence": "clear",
            "status": "ready_for_feedback",
        },
        data_root=data_root,
    )
    feedback_file = tmp_path / "assistant_feedback.json"
    feedback_file.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "question_no": 2,
                        "assistant_feedback": {
                            "diagnosis_text": "Stale diagnosis.",
                            "provisional_error_tags": ["stale"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    import_assistant_feedback("attempt-001", feedback_file, data_root=data_root)

    result = regrade_attempt("attempt-001", {2: 3}, data_root=data_root)

    review = load_review_record("attempt-001", 2, data_root=data_root)
    assert result.wrong_question_numbers == [2]
    assert review.grading.selected_choice == 3
    assert review.grading.correct_choice == 4
    assert review.user_self_review.reasoning_text == "I entered the wrong selected answer."
    assert review.user_self_review.current_reflection == "The original answer entry was stale."
    assert review.user_self_review.memory_confidence == MemoryConfidence.CLEAR
    assert review.assistant_feedback is None
    assert review.status == AttemptReviewStatus.USER_ENTERED


def test_regrade_reports_only_reviews_touched_by_update(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 1, 2: 4, 3: 5})
    create_attempt_record("attempt-001", exam_id, "111", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    untouched_path = review_path("attempt-001", 2, data_root=data_root)
    untouched_before = json.loads(untouched_path.read_text(encoding="utf-8"))

    result = regrade_attempt("attempt-001", {3: 4}, data_root=data_root)

    untouched_after = json.loads(untouched_path.read_text(encoding="utf-8"))
    assert result.wrong_question_numbers == [2, 3]
    assert result.updated_question_numbers == [3]
    assert untouched_after == untouched_before


def test_regrade_archives_review_when_question_becomes_correct(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 1, 2: 4, 3: 5})
    create_attempt_record("attempt-001", exam_id, "125", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    update_user_self_review(
        "attempt-001",
        2,
        {"reasoning_text": "Typo in answer entry.", "status": "ready_for_feedback"},
        data_root=data_root,
    )

    result = regrade_attempt("attempt-001", {2: 4}, data_root=data_root)

    assert result.score == 3
    assert result.wrong_question_numbers == []
    assert result.archived_question_numbers == [2]
    assert not review_path("attempt-001", 2, data_root=data_root).exists()
    archived_path = archived_reviews_dir("attempt-001", data_root=data_root) / "q02.review.json"
    assert archived_path.exists()
    archived = json.loads(archived_path.read_text(encoding="utf-8"))
    assert archived["user_self_review"]["reasoning_text"] == "Typo in answer entry."


def test_regrade_rejects_unrecorded_question(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 1, 2: 4, 3: 5})
    create_attempt_record("attempt-001", exam_id, "125", data_root=data_root)

    with pytest.raises(AttemptReviewError, match="unrecorded"):
        regrade_attempt("attempt-001", {4: 2}, data_root=data_root)


def test_assistant_feedback_import_preserves_user_self_review(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    update_user_self_review(
        "attempt-001",
        1,
        {"reasoning_text": "I matched the wrong condition.", "status": "ready_for_feedback"},
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
    assert review.user_self_review.reasoning_text == "I matched the wrong condition."
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
            {"reasoning_text": "Surface match.", "status": "feedback_added"},
            data_root=data_root,
        )


def test_export_feedback_bundle_contains_user_review_not_resolution(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    _write_questions_jsonl(data_root, exam_id, {1: 3})
    question_path = data_root / "canonical" / exam_id / "questions.jsonl"
    question = json.loads(question_path.read_text(encoding="utf-8").splitlines()[0])
    question["passage_id"] = f"{exam_id}-passage-001"
    question_path.write_text(json.dumps(question) + "\n", encoding="utf-8")
    _write_passages_jsonl(data_root, exam_id)
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
    assert bundle["reviews"][0]["question"]["passage_text"] == "Passage text\n\nSecond paragraph"
    assert "user_resolution" not in bundle["reviews"][0]


def test_new_review_json_omits_removed_self_review_fields(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)

    initialize_attempt_reviews("attempt-001", data_root=data_root)

    payload = json.loads(review_path("attempt-001", 1, data_root=data_root).read_text(encoding="utf-8"))
    self_review = payload["user_self_review"]
    assert set(self_review) >= {"reasoning_text", "current_reflection", "memory_confidence"}
    assert "why_selected" not in self_review
    assert "decisive_condition" not in self_review
    assert "why_rejected_correct" not in self_review
    assert "condition_notes" not in self_review


def test_update_user_self_review_accepts_simplified_fields(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)

    review = update_user_self_review(
        "attempt-001",
        1,
        {
            "reasoning_text": "I remembered the surface match.",
            "current_reflection": "I should compare conditions.",
            "memory_confidence": "unclear",
            "status": "ready_for_feedback",
        },
        data_root=data_root,
    )

    assert review.user_self_review.reasoning_text == "I remembered the surface match."
    assert review.user_self_review.current_reflection == "I should compare conditions."
    assert review.user_self_review.memory_confidence == MemoryConfidence.UNCLEAR


def test_update_user_self_review_preserves_ready_status_when_status_omitted(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_answer_key(data_root, exam_id, {1: 3})
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    update_user_self_review(
        "attempt-001",
        1,
        {"reasoning_text": "Initial reasoning.", "status": "ready_for_feedback"},
        data_root=data_root,
    )

    review = update_user_self_review(
        "attempt-001",
        1,
        {"current_reflection": "Later note."},
        data_root=data_root,
    )

    assert review.status == AttemptReviewStatus.READY_FOR_FEEDBACK
    assert review.user_self_review.reasoning_text == "Initial reasoning."
    assert review.user_self_review.current_reflection == "Later note."


def test_migrate_self_review_merges_legacy_fields_and_preserves_feedback(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    review_dir = data_root / "reviews" / "attempt-001"
    review_dir.mkdir(parents=True)
    path = review_dir / "q01.review.json"
    payload = {
        "attempt_id": "attempt-001",
        "exam_id": "leet-2026-reasoning-even",
        "question_no": 1,
        "status": "feedback_added",
        "grading": {"selected_choice": 1, "correct_choice": 3, "is_correct": False},
        "user_self_review": {
            "reasoning_text": "Original full reasoning.",
            "why_selected": "Choice 1 looked closest.",
            "decisive_condition": "The final condition.",
            "why_rejected_correct": "I thought choice 3 was too broad.",
            "current_reflection": "I missed a constraint.",
            "condition_notes": "Low confidence.",
            "created_by": "user",
            "created_at": "2026-07-06T10:00:00",
            "updated_at": "2026-07-06T10:05:00",
        },
        "assistant_feedback": {
            "diagnosis_text": "Existing feedback.",
            "evidence": ["e1"],
            "provisional_error_tags": ["tag"],
            "correction_rule": "Check constraints.",
            "created_by": "assistant",
            "created_at": "2026-07-06T10:10:00",
            "updated_at": "2026-07-06T10:10:00",
        },
        "user_resolution": {
            "status": "accepted",
            "final_error_tags": ["tag"],
            "note": "ok",
            "created_by": "user",
            "created_at": "2026-07-06T10:15:00",
            "updated_at": "2026-07-06T10:15:00",
        },
        "created_at": "2026-07-06T10:00:00",
        "updated_at": "2026-07-06T10:20:00",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = migrate_self_review_files(data_root=data_root)
    migrated_once = json.loads(path.read_text(encoding="utf-8"))
    second_result = migrate_self_review_files(data_root=data_root)
    migrated_twice = json.loads(path.read_text(encoding="utf-8"))

    assert result.scanned == 1
    assert result.migrated == 1
    assert second_result.scanned == 1
    assert second_result.migrated == 0
    assert migrated_once == migrated_twice
    assert migrated_once["status"] == "feedback_added"
    assert migrated_once["assistant_feedback"] == payload["assistant_feedback"]
    assert migrated_once["user_resolution"] == payload["user_resolution"]
    assert migrated_once["user_self_review"]["current_reflection"] == "I missed a constraint."
    assert migrated_once["user_self_review"]["memory_confidence"] == "partial"
    assert migrated_once["user_self_review"]["created_at"] == "2026-07-06T10:00:00"
    assert migrated_once["user_self_review"]["updated_at"] == "2026-07-06T10:05:00"
    assert "[당시 풀이 사고]\nOriginal full reasoning." in migrated_once["user_self_review"]["reasoning_text"]
    assert "[선택 이유]\nChoice 1 looked closest." in migrated_once["user_self_review"]["reasoning_text"]
    assert "[결정적으로 본 조건]\nThe final condition." in migrated_once["user_self_review"]["reasoning_text"]
    assert "[정답 선지를 배제한 이유]\nI thought choice 3 was too broad." in migrated_once["user_self_review"]["reasoning_text"]
    assert "[추가 메모]\nLow confidence." in migrated_once["user_self_review"]["reasoning_text"]
    assert "why_selected" not in migrated_once["user_self_review"]
    assert "decisive_condition" not in migrated_once["user_self_review"]
    assert "why_rejected_correct" not in migrated_once["user_self_review"]
    assert "condition_notes" not in migrated_once["user_self_review"]
