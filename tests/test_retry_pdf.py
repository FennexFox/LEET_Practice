from __future__ import annotations

import json
from pathlib import Path

import pytest

from leet_practice.retry_pdf import create_retry_pdf_bundle, select_retry_questions
from leet_practice.retry_results import RetryOutcome, RetryQuestionStatus


def _tag_record(
    name: str,
    tag: str,
    *,
    question_no: int,
    confidence: str = "high",
    holdout: bool = False,
) -> dict[str, object]:
    return {
        "review_file": f"data/reviews/exam/{name}.review.json",
        "exam_id": "2025 언어이해 홀수형",
        "year": 2025,
        "section": "언어이해",
        "question_no": question_no,
        "question_id": f"q{question_no}",
        "selected_choice": 2,
        "correct_choice": 1,
        "is_correct": False,
        "provisional_tags": {"primary": tag, "secondary": [], "confidence": confidence},
        "tag_rationale": f"reason {name}",
        "holdout": holdout,
        "use_for_tag_frequency": not holdout,
    }


def test_recommendation_balances_weak_tags_and_excludes_holdouts() -> None:
    records = [
        _tag_record("a1", "A", question_no=1),
        _tag_record("a2", "A", question_no=2, confidence="low"),
        _tag_record("a3", "A", question_no=3),
        _tag_record("b1", "B", question_no=4),
        _tag_record("b2", "B", question_no=5),
        _tag_record("c1", "C", question_no=6),
        _tag_record("held", "D", question_no=7, holdout=True),
    ]

    selected, skipped = select_retry_questions(records, data_root=Path("data"), limit=5)

    assert skipped == []
    assert [row["review_file"] for row in selected] == [
        "data/reviews/exam/a1.review.json",
        "data/reviews/exam/b1.review.json",
        "data/reviews/exam/c1.review.json",
        "data/reviews/exam/a3.review.json",
        "data/reviews/exam/b2.review.json",
    ]


def test_explicit_selection_preserves_order_and_reports_filtered_items() -> None:
    records = [
        _tag_record("first", "A", question_no=1),
        _tag_record("second", "B", question_no=2),
        _tag_record("held", "C", question_no=3, holdout=True),
    ]

    selected, skipped = select_retry_questions(
        records,
        data_root=Path("data"),
        review_files=[
            "data/reviews/exam/second.review.json",
            "data/reviews/exam/first.review.json",
            "data/reviews/exam/held.review.json",
            "data/reviews/exam/missing.review.json",
        ],
    )

    assert [row["review_file"] for row in selected] == [
        "data/reviews/exam/second.review.json",
        "data/reviews/exam/first.review.json",
    ]
    assert [item["reason"] for item in skipped] == [
        "excluded by filters or holdout policy",
        "tagging record not found",
    ]


def _status(
    review_file: str,
    outcome: RetryOutcome,
    *,
    selected_choice: int | None,
) -> RetryQuestionStatus:
    return RetryQuestionStatus(
        review_file=review_file,
        latest_outcome=outcome,
        attempt_count=1 if selected_choice is not None else 0,
        session_count=1,
        last_selected_choice=selected_choice,
        correct_choice=1,
        last_answered_at="2026-07-13T00:00:00+00:00",
        last_session_id="retry-session",
    )


def test_retry_history_prioritizes_incorrect_and_excludes_latest_correct() -> None:
    records = [
        _tag_record("new", "A", question_no=1),
        _tag_record("correct", "B", question_no=2),
        _tag_record("wrong", "C", question_no=3),
        _tag_record("skipped", "D", question_no=4),
    ]
    statuses = {
        "data/reviews/exam/correct.review.json": _status(
            "data/reviews/exam/correct.review.json", RetryOutcome.CORRECT, selected_choice=1
        ),
        "data/reviews/exam/wrong.review.json": _status(
            "data/reviews/exam/wrong.review.json", RetryOutcome.INCORRECT, selected_choice=2
        ),
        "data/reviews/exam/skipped.review.json": _status(
            "data/reviews/exam/skipped.review.json", RetryOutcome.SKIPPED, selected_choice=None
        ),
    }

    selected, _ = select_retry_questions(
        records,
        data_root=Path("data"),
        limit=4,
        retry_statuses=statuses,
    )

    assert [row["review_file"] for row in selected] == [
        "data/reviews/exam/wrong.review.json",
        "data/reviews/exam/skipped.review.json",
        "data/reviews/exam/new.review.json",
    ]


def test_include_completed_restores_correct_questions_after_unresolved() -> None:
    records = [
        _tag_record("correct", "A", question_no=1),
        _tag_record("new", "B", question_no=2),
    ]
    review_file = "data/reviews/exam/correct.review.json"
    statuses = {review_file: _status(review_file, RetryOutcome.CORRECT, selected_choice=1)}

    selected, _ = select_retry_questions(
        records,
        data_root=Path("data"),
        limit=2,
        retry_statuses=statuses,
        include_completed=True,
    )

    assert [row["review_file"] for row in selected] == [
        "data/reviews/exam/new.review.json",
        review_file,
    ]


def test_bundle_separates_problem_text_from_answer_appendix_and_writes_manifest(tmp_path: Path) -> None:
    reportlab = pytest.importorskip("reportlab")
    pytest.importorskip("pypdf")
    from pypdf import PdfReader

    data_root = tmp_path / "data"
    tagging_dir = data_root / "tagging"
    review_dir = data_root / "reviews" / "exam"
    canonical_dir = data_root / "canonical" / "2025 언어이해"
    tagging_dir.mkdir(parents=True)
    review_dir.mkdir(parents=True)
    canonical_dir.mkdir(parents=True)
    records = [
        _tag_record("q01", "ATTENTION", question_no=1),
        _tag_record("q02", "VERIFICATION", question_no=2),
    ]
    (tagging_dir / "provisional_tags.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    for question_no in (1, 2):
        (review_dir / f"q{question_no:02d}.review.json").write_text(
            json.dumps({"grading": {"selected_choice": 2, "correct_choice": 1}}), encoding="utf-8"
        )
    (canonical_dir / "questions.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "id": f"q{question_no}",
                    "exam_id": "2025 언어이해",
                    "question_no": question_no,
                    "passage_id": "p1",
                    "stem": f"Which statement is correct for question {question_no}?",
                    "choices": [
                        {"choice_no": number, "text": f"Choice {number}", "is_correct": number == 1}
                        for number in range(1, 6)
                    ],
                    "correct_answer": 1,
                }
            )
            for question_no in (1, 2)
        )
        + "\n",
        encoding="utf-8",
    )
    (canonical_dir / "passages.jsonl").write_text(
        json.dumps({"id": "p1", "body_text": "Shared passage text."}) + "\n",
        encoding="utf-8",
    )
    font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    output_path = tmp_path / "output" / "retry.pdf"

    bundle = create_retry_pdf_bundle(
        data_root=data_root,
        output_path=output_path,
        font_path=font_path,
        title="Retry Workbook",
    )

    reader = PdfReader(str(bundle.pdf_path))
    assert len(reader.pages) >= 2
    assert "Which statement is correct" in reader.pages[0].extract_text()
    assert "Correct 1" not in reader.pages[0].extract_text()
    assert "ATTENTION" not in reader.pages[0].extract_text()
    all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "ATTENTION" in all_text
    assert all_text.count("Shared passage text.") == 1
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert bundle.session_id == manifest["session_id"]
    assert manifest["schema_version"] == 2
    assert manifest["settings"]["include_completed"] is False
    assert manifest["settings"]["selection_mode"] == "recommended"
    assert manifest["selected"][0]["review_file"] == "data/reviews/exam/q01.review.json"
    assert manifest["tag_summary"] == {"ATTENTION": 1, "VERIFICATION": 1}
