from __future__ import annotations

import json
from pathlib import Path

import pytest

from leet_practice.retry_results import (
    RetryOutcome,
    RetryResultError,
    load_latest_retry_statuses,
    load_retry_manifest,
    load_retry_session_result,
    retry_result_path,
    save_retry_session_result,
)


def _write_manifest(
    tmp_path: Path,
    *,
    session_id: str = "retry-session-1",
    include_session_id: bool = True,
) -> Path:
    path = tmp_path / "output" / "pdf" / "retry-pdfs" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "title": "집중력 재점검",
        "selected": [
            {
                "review_file": "data/reviews/exam/q01.review.json",
                "question_id": "q1",
                "year": 2025,
                "section": "언어이해",
                "question_no": 1,
                "correct_choice": 1,
            },
            {
                "review_file": "data/reviews/exam/q02.review.json",
                "question_id": "q2",
                "year": 2025,
                "section": "언어이해",
                "question_no": 2,
                "correct_choice": 3,
            },
            {
                "review_file": "data/reviews/exam/q03.review.json",
                "question_id": "q3",
                "year": 2025,
                "section": "언어이해",
                "question_no": 3,
                "correct_choice": 5,
            },
        ],
    }
    if include_session_id:
        payload["session_id"] = session_id
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _answers(first: int | None = 1, second: int | None = 2, third: int | None = None):
    return [
        {"review_file": "data/reviews/exam/q01.review.json", "selected_choice": first},
        {"review_file": "data/reviews/exam/q02.review.json", "selected_choice": second, "note": "조건 재확인"},
        {"review_file": "data/reviews/exam/q03.review.json", "selected_choice": third},
    ]


def test_save_grades_every_manifest_item_and_aggregates_status(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    manifest = _write_manifest(tmp_path)

    result = save_retry_session_result(manifest, _answers(), data_root=data_root)

    assert [item.outcome for item in result.items] == [
        RetryOutcome.CORRECT,
        RetryOutcome.INCORRECT,
        RetryOutcome.SKIPPED,
    ]
    stored = load_retry_session_result(retry_result_path(result.session_id, data_root=data_root))
    assert stored == result
    statuses = load_latest_retry_statuses(data_root=data_root)
    assert statuses["data/reviews/exam/q01.review.json"].latest_outcome is RetryOutcome.CORRECT
    assert statuses["data/reviews/exam/q02.review.json"].latest_outcome is RetryOutcome.INCORRECT
    assert statuses["data/reviews/exam/q03.review.json"].latest_outcome is RetryOutcome.SKIPPED
    assert statuses["data/reviews/exam/q03.review.json"].attempt_count == 0


def test_resubmitting_same_session_corrects_it_without_duplicating_history(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    manifest = _write_manifest(tmp_path)
    original = save_retry_session_result(manifest, _answers(), data_root=data_root)

    corrected = save_retry_session_result(manifest, _answers(second=3, third=5), data_root=data_root)

    assert corrected.created_at == original.created_at
    assert [item.outcome for item in corrected.items] == [
        RetryOutcome.CORRECT,
        RetryOutcome.CORRECT,
        RetryOutcome.CORRECT,
    ]
    statuses = load_latest_retry_statuses(data_root=data_root)
    assert statuses["data/reviews/exam/q02.review.json"].session_count == 1
    assert statuses["data/reviews/exam/q02.review.json"].attempt_count == 1


def test_later_session_supersedes_earlier_result_and_preserves_counts(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    first_manifest = _write_manifest(tmp_path, session_id="retry-session-a")
    first = save_retry_session_result(first_manifest, _answers(first=1), data_root=data_root)
    second_manifest = _write_manifest(tmp_path, session_id="retry-session-b")
    second = save_retry_session_result(second_manifest, _answers(first=2), data_root=data_root)
    first_path = retry_result_path(first.session_id, data_root=data_root)
    second_path = retry_result_path(second.session_id, data_root=data_root)
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))
    first_payload["updated_at"] = "2026-07-12T00:00:00+00:00"
    second_payload["updated_at"] = "2026-07-13T00:00:00+00:00"
    for item in first_payload["items"]:
        item["answered_at"] = first_payload["updated_at"]
    for item in second_payload["items"]:
        item["answered_at"] = second_payload["updated_at"]
    first_path.write_text(json.dumps(first_payload), encoding="utf-8")
    second_path.write_text(json.dumps(second_payload), encoding="utf-8")

    status = load_latest_retry_statuses(data_root=data_root)["data/reviews/exam/q01.review.json"]

    assert status.latest_outcome is RetryOutcome.INCORRECT
    assert status.session_count == 2
    assert status.attempt_count == 2


def test_manifest_without_session_id_uses_safe_filename(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, session_id="legacy-retry", include_session_id=False)

    assert load_retry_manifest(path)["session_id"] == "legacy-retry"


@pytest.mark.parametrize(
    "answers",
    [
        _answers()[:-1],
        [*_answers(), {"review_file": "data/reviews/exam/q99.review.json", "selected_choice": 1}],
        [*_answers()[:1], *_answers()[:1], *_answers()[2:]],
        _answers(second=6),
    ],
)
def test_save_rejects_incomplete_unknown_duplicate_or_invalid_answers(tmp_path: Path, answers) -> None:
    manifest = _write_manifest(tmp_path)

    with pytest.raises(RetryResultError):
        save_retry_session_result(manifest, answers, data_root=tmp_path / "data")

    assert not (tmp_path / "data" / "retry_attempts").exists()


def test_result_path_rejects_traversal() -> None:
    with pytest.raises(RetryResultError):
        retry_result_path("../outside")


def test_missing_retry_attempt_directory_has_empty_status_index(tmp_path: Path) -> None:
    assert load_latest_retry_statuses(data_root=tmp_path / "data") == {}
