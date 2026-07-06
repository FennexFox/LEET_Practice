"""Attempt self-review workflow and file-based assistant feedback handoff."""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field, ValidationError

from leet_practice.models import (
    AssistantFeedback,
    AttemptChoiceAnswer,
    AttemptRecord,
    AttemptReviewRecord,
    AttemptReviewStatus,
    ReviewGrading,
    UserResolution,
    UserResolutionStatus,
    UserSelfReview,
)

_attempt_review_lock = threading.RLock()


class AttemptReviewError(RuntimeError):
    """Raised when attempt-review data is missing or invalid."""


class AnswerKey(BaseModel):
    """Resolved canonical answers and their source."""

    answers: dict[int, int]
    source: str


class ReviewQuestionContext(BaseModel):
    """Canonical question context used by the attempt-review UI and exports."""

    question_no: int = Field(gt=0)
    question_id: str | None = None
    passage_id: str | None = None
    stem: str | None = None
    choices: list[dict[str, Any]] = Field(default_factory=list)


class AttemptReviewState(BaseModel):
    """Aggregated state for the browser workbench."""

    attempt: AttemptRecord
    answer_key_source: str
    score: int
    total: int
    wrong_question_numbers: list[int]
    reviews: list[AttemptReviewRecord]
    questions: dict[int, ReviewQuestionContext] = Field(default_factory=dict)


def attempts_dir(*, data_root: Path = Path("data")) -> Path:
    return data_root / "attempts"


def attempt_path(attempt_id: str, *, data_root: Path = Path("data")) -> Path:
    return attempts_dir(data_root=data_root) / f"{attempt_id}.json"


def attempt_reviews_dir(attempt_id: str, *, data_root: Path = Path("data")) -> Path:
    return data_root / "reviews" / attempt_id


def review_path(attempt_id: str, question_no: int, *, data_root: Path = Path("data")) -> Path:
    return attempt_reviews_dir(attempt_id, data_root=data_root) / f"q{question_no:03d}.review.json"


def canonical_dir(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return data_root / "canonical" / exam_id


def answer_key_path(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return canonical_dir(exam_id, data_root=data_root) / "answer_key.json"


def questions_path(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return canonical_dir(exam_id, data_root=data_root) / "questions.jsonl"


def _now() -> datetime:
    return datetime.now()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _choice_from_value(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid answer choices")
    if isinstance(value, int):
        choice = value
    elif isinstance(value, str) and value.strip().isdigit():
        choice = int(value.strip())
    else:
        raise ValueError(f"unsupported answer choice value: {value!r}")
    if choice < 1 or choice > 5:
        raise ValueError(f"answer choice must be between 1 and 5: {choice}")
    return choice


def _question_no_from_value(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid question numbers")
    if isinstance(value, int):
        question_no = value
    elif isinstance(value, str) and value.strip().isdigit():
        question_no = int(value.strip())
    else:
        raise ValueError(f"unsupported question number value: {value!r}")
    if question_no <= 0:
        raise ValueError(f"question number must be positive: {question_no}")
    return question_no


def _answer_from_mapping_item(item: dict[str, Any]) -> tuple[int, int] | None:
    question_no_raw = item.get("question_no", item.get("number", item.get("question")))
    answer_raw = item.get(
        "correct_choice",
        item.get("correct_answer", item.get("answer", item.get("choice"))),
    )
    if question_no_raw is None or answer_raw is None:
        return None
    return _question_no_from_value(question_no_raw), _choice_from_value(answer_raw)


def _parse_answer_payload(payload: Any) -> dict[int, int]:
    if isinstance(payload, list):
        answers: dict[int, int] = {}
        for index, item in enumerate(payload, start=1):
            if isinstance(item, dict):
                parsed = _answer_from_mapping_item(item)
                if parsed is None:
                    raise AttemptReviewError(f"Unsupported answer row at index {index}: {item!r}")
                question_no, choice = parsed
            else:
                question_no, choice = index, _choice_from_value(item)
            answers[question_no] = choice
        return answers

    if not isinstance(payload, dict):
        raise AttemptReviewError("Answer key must be a JSON object or list.")

    for key in ("answers", "answer_key", "correct_answers", "questions"):
        if key in payload:
            return _parse_answer_payload(payload[key])

    if all(str(key).isdigit() for key in payload):
        return {_question_no_from_value(key): _choice_from_value(value) for key, value in payload.items()}

    parsed_item = _answer_from_mapping_item(payload)
    if parsed_item is not None:
        question_no, choice = parsed_item
        return {question_no: choice}

    raise AttemptReviewError("Unsupported answer_key.json shape.")


def _load_answer_key_json(path: Path) -> dict[int, int]:
    try:
        return _parse_answer_payload(_read_json(path))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AttemptReviewError(f"Invalid answer key {path}: {exc}") from exc


def load_question_contexts(exam_id: str, *, data_root: Path = Path("data")) -> dict[int, ReviewQuestionContext]:
    path = questions_path(exam_id, data_root=data_root)
    if not path.exists():
        return {}
    contexts: dict[int, ReviewQuestionContext] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            question_no = _question_no_from_value(row["question_no"])
        except (KeyError, json.JSONDecodeError, ValueError) as exc:
            raise AttemptReviewError(f"Invalid questions.jsonl row {line_no}: {exc}") from exc
        contexts[question_no] = ReviewQuestionContext(
            question_no=question_no,
            question_id=row.get("id"),
            passage_id=row.get("passage_id"),
            stem=row.get("stem"),
            choices=list(row.get("choices") or []),
        )
    return contexts


def _load_questions_answers(exam_id: str, *, data_root: Path = Path("data")) -> dict[int, int]:
    path = questions_path(exam_id, data_root=data_root)
    if not path.exists():
        return {}
    answers: dict[int, int] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            parsed = _answer_from_mapping_item(row)
        except (json.JSONDecodeError, ValueError) as exc:
            raise AttemptReviewError(f"Invalid questions.jsonl row {line_no}: {exc}") from exc
        if parsed is None:
            continue
        question_no, choice = parsed
        answers[question_no] = choice
    return answers


def load_answer_key(exam_id: str, *, data_root: Path = Path("data")) -> AnswerKey:
    key_path = answer_key_path(exam_id, data_root=data_root)
    json_answers = _load_answer_key_json(key_path) if key_path.exists() else {}
    question_answers = _load_questions_answers(exam_id, data_root=data_root)

    if json_answers and question_answers:
        shared_questions = sorted(set(json_answers) & set(question_answers))
        disagreements = [
            question_no
            for question_no in shared_questions
            if json_answers[question_no] != question_answers[question_no]
        ]
        if disagreements:
            question_no = disagreements[0]
            raise AttemptReviewError(
                "Canonical answer sources disagree for "
                f"question {question_no}: answer_key.json={json_answers[question_no]}, "
                f"questions.jsonl={question_answers[question_no]}"
            )
        return AnswerKey(answers=json_answers, source=str(key_path))

    if json_answers:
        return AnswerKey(answers=json_answers, source=str(key_path))
    if question_answers:
        return AnswerKey(answers=question_answers, source=str(questions_path(exam_id, data_root=data_root)))
    raise AttemptReviewError(
        f"No canonical answers found for {exam_id}. Expected {key_path} or {questions_path(exam_id, data_root=data_root)}."
    )


def parse_answer_string(answers: str) -> list[int]:
    compact = "".join(char for char in answers if not char.isspace())
    if not compact:
        raise AttemptReviewError("Answer string is empty.")
    invalid = sorted({char for char in compact if char not in "12345"})
    if invalid:
        raise AttemptReviewError(f"Answer string contains invalid choice marker(s): {''.join(invalid)}")
    return [int(char) for char in compact]


def create_attempt_record(
    attempt_id: str,
    exam_id: str,
    answers: str | list[int],
    *,
    data_root: Path = Path("data"),
    mode: str = "real",
    notes: str | None = None,
    overwrite: bool = False,
) -> AttemptRecord:
    path = attempt_path(attempt_id, data_root=data_root)
    if path.exists() and not overwrite:
        raise AttemptReviewError(f"Attempt already exists: {path}")
    selected = parse_answer_string(answers) if isinstance(answers, str) else answers
    if mode == "real":
        answer_key = load_answer_key(exam_id, data_root=data_root)
        expected_count = len(answer_key.answers)
        if len(selected) != expected_count:
            raise AttemptReviewError(
                f"Real-mode attempt has {len(selected)} answer(s), but canonical answer key has {expected_count}."
            )
    now = _now()
    try:
        attempt = AttemptRecord(
            id=attempt_id,
            exam_id=exam_id,
            mode=mode,  # type: ignore[arg-type]
            answers=[
                AttemptChoiceAnswer(question_no=index, selected_choice=choice)
                for index, choice in enumerate(selected, start=1)
            ],
            notes=notes,
            created_at=now,
            updated_at=now,
        )
    except ValidationError as exc:
        raise AttemptReviewError(f"Invalid attempt record: {exc}") from exc
    save_attempt_record(attempt, data_root=data_root)
    return attempt


def load_attempt_record(attempt_id: str, *, data_root: Path = Path("data")) -> AttemptRecord:
    path = attempt_path(attempt_id, data_root=data_root)
    if not path.exists():
        raise AttemptReviewError(f"Attempt record does not exist: {path}")
    try:
        return AttemptRecord.model_validate(_read_json(path))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AttemptReviewError(f"Invalid attempt record {path}: {exc}") from exc


def save_attempt_record(attempt: AttemptRecord, *, data_root: Path = Path("data")) -> Path:
    updated = attempt.model_copy(update={"updated_at": _now()})
    path = attempt_path(updated.id, data_root=data_root)
    _write_json(path, updated.model_dump(mode="json"))
    return path


def grade_attempt(attempt: AttemptRecord, *, data_root: Path = Path("data")) -> tuple[AnswerKey, list[ReviewGrading]]:
    answer_key = load_answer_key(attempt.exam_id, data_root=data_root)
    grading: list[ReviewGrading] = []
    for answer in attempt.answers:
        if answer.question_no not in answer_key.answers:
            raise AttemptReviewError(
                f"No canonical answer for question {answer.question_no} in {answer_key.source}."
            )
        grading.append(
            ReviewGrading(
                selected_choice=answer.selected_choice,
                correct_choice=answer_key.answers[answer.question_no],
            )
        )
    return answer_key, grading


def _initial_review_from_answer(
    attempt: AttemptRecord,
    answer: AttemptChoiceAnswer,
    correct_choice: int,
    question_context: ReviewQuestionContext | None,
) -> AttemptReviewRecord:
    return AttemptReviewRecord(
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        question_no=answer.question_no,
        question_id=question_context.question_id if question_context else None,
        grading=ReviewGrading(
            selected_choice=answer.selected_choice,
            correct_choice=correct_choice,
        ),
    )


def load_review_record(
    attempt_id: str,
    question_no: int,
    *,
    data_root: Path = Path("data"),
) -> AttemptReviewRecord:
    path = review_path(attempt_id, question_no, data_root=data_root)
    if not path.exists():
        raise AttemptReviewError(f"Review record does not exist: {path}")
    try:
        return AttemptReviewRecord.model_validate(_read_json(path))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AttemptReviewError(f"Invalid review record {path}: {exc}") from exc


def save_review_record(review: AttemptReviewRecord, *, data_root: Path = Path("data")) -> Path:
    updated = review.model_copy(update={"updated_at": _now()})
    path = review_path(updated.attempt_id, updated.question_no, data_root=data_root)
    _write_json(path, updated.model_dump(mode="json"))
    return path


def initialize_attempt_reviews(
    attempt_id: str,
    *,
    data_root: Path = Path("data"),
    include_correct: bool = False,
) -> AttemptReviewState:
    with _attempt_review_lock:
        attempt = load_attempt_record(attempt_id, data_root=data_root)
        answer_key, grading = grade_attempt(attempt, data_root=data_root)
        contexts = load_question_contexts(attempt.exam_id, data_root=data_root)
        reviews: list[AttemptReviewRecord] = []

        for answer, grade in zip(attempt.answers, grading, strict=True):
            if grade.is_correct and not include_correct:
                continue
            path = review_path(attempt.id, answer.question_no, data_root=data_root)
            if path.exists():
                review = load_review_record(attempt.id, answer.question_no, data_root=data_root)
            else:
                review = _initial_review_from_answer(
                    attempt,
                    answer,
                    grade.correct_choice,
                    contexts.get(answer.question_no),
                )
                save_review_record(review, data_root=data_root)
            reviews.append(review)

        wrong_question_numbers = [
            answer.question_no
            for answer, grade in zip(attempt.answers, grading, strict=True)
            if not grade.is_correct
        ]
        score = len(attempt.answers) - len(wrong_question_numbers)
        return AttemptReviewState(
            attempt=attempt,
            answer_key_source=answer_key.source,
            score=score,
            total=len(attempt.answers),
            wrong_question_numbers=wrong_question_numbers,
            reviews=sorted(reviews, key=lambda review: review.question_no),
            questions=contexts,
        )


def update_user_self_review(
    attempt_id: str,
    question_no: int,
    payload: dict[str, Any],
    *,
    data_root: Path = Path("data"),
) -> AttemptReviewRecord:
    allowed = {
        "reasoning_text",
        "why_selected",
        "decisive_condition",
        "why_rejected_correct",
        "current_reflection",
        "condition_notes",
    }
    with _attempt_review_lock:
        review = load_review_record(attempt_id, question_no, data_root=data_root)
        current = review.user_self_review.model_dump()
        for key in allowed:
            if key in payload:
                current[key] = payload[key] or ""
        current["updated_at"] = _now()
        if not current.get("created_at"):
            current["created_at"] = current["updated_at"]
        status_raw = payload.get("status")
        status = AttemptReviewStatus(status_raw) if status_raw else AttemptReviewStatus.USER_ENTERED
        if status not in {AttemptReviewStatus.USER_ENTERED, AttemptReviewStatus.READY_FOR_FEEDBACK}:
            raise AttemptReviewError(
                "Self-review status updates may only set user_entered or ready_for_feedback."
            )
        updated = review.model_copy(
            update={
                "status": status,
                "user_self_review": UserSelfReview.model_validate(current),
                "updated_at": _now(),
            }
        )
        save_review_record(updated, data_root=data_root)
        return updated


def update_user_resolution(
    attempt_id: str,
    question_no: int,
    payload: dict[str, Any],
    *,
    data_root: Path = Path("data"),
) -> AttemptReviewRecord:
    with _attempt_review_lock:
        review = load_review_record(attempt_id, question_no, data_root=data_root)
        current = review.user_resolution.model_dump()
        if "status" in payload:
            current["status"] = UserResolutionStatus(payload["status"])
        if "final_error_tags" in payload:
            current["final_error_tags"] = list(payload["final_error_tags"] or [])
        if "note" in payload:
            current["note"] = payload["note"]
        current["updated_at"] = _now()
        status = AttemptReviewStatus.RESOLVED if current["status"] != UserResolutionStatus.PENDING else review.status
        updated = review.model_copy(
            update={
                "status": status,
                "user_resolution": UserResolution.model_validate(current),
                "updated_at": _now(),
            }
        )
        save_review_record(updated, data_root=data_root)
        return updated


def export_feedback_bundle(
    attempt_id: str,
    *,
    data_root: Path = Path("data"),
    out_file: Path | None = None,
) -> Path:
    state = initialize_attempt_reviews(attempt_id, data_root=data_root)
    out_file = out_file or (attempt_reviews_dir(attempt_id, data_root=data_root) / "feedback_request.json")
    reviews = []
    for review in state.reviews:
        if review.status not in {
            AttemptReviewStatus.USER_ENTERED,
            AttemptReviewStatus.READY_FOR_FEEDBACK,
            AttemptReviewStatus.FEEDBACK_ADDED,
        }:
            continue
        question = state.questions.get(review.question_no)
        reviews.append(
            {
                "question_no": review.question_no,
                "question": question.model_dump(mode="json") if question else None,
                "grading": review.grading.model_dump(mode="json"),
                "user_self_review": review.user_self_review.model_dump(mode="json"),
            }
        )
    bundle = {
        "artifact_type": "leet_practice_attempt_review_feedback_request",
        "attempt_id": state.attempt.id,
        "exam_id": state.attempt.exam_id,
        "created_at": _now().isoformat(),
        "reviews": reviews,
    }
    _write_json(out_file, bundle)
    return out_file


def _feedback_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("reviews", "feedback", "assistant_feedback"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if all(str(key).isdigit() for key in payload):
            return [
                {"question_no": int(key), "assistant_feedback": value}
                for key, value in payload.items()
                if isinstance(value, dict)
            ]
    raise AttemptReviewError("Assistant feedback file must contain a review list or question mapping.")


def import_assistant_feedback(
    attempt_id: str,
    feedback_file: Path,
    *,
    data_root: Path = Path("data"),
) -> list[AttemptReviewRecord]:
    try:
        payload = _read_json(feedback_file)
    except json.JSONDecodeError as exc:
        raise AttemptReviewError(f"Invalid assistant feedback JSON {feedback_file}: {exc}") from exc

    updated_reviews: list[AttemptReviewRecord] = []
    with _attempt_review_lock:
        for item in _feedback_items(payload):
            question_no = _question_no_from_value(item.get("question_no", item.get("question")))
            feedback_payload = item.get("assistant_feedback", item)
            if not isinstance(feedback_payload, dict):
                raise AttemptReviewError(f"Assistant feedback for question {question_no} must be an object.")
            feedback = AssistantFeedback.model_validate(
                {
                    "diagnosis_text": feedback_payload.get("diagnosis_text", ""),
                    "evidence": feedback_payload.get("evidence", []),
                    "provisional_error_tags": feedback_payload.get("provisional_error_tags", []),
                    "correction_rule": feedback_payload.get("correction_rule", ""),
                    "created_by": "assistant",
                    "created_at": feedback_payload.get("created_at") or _now(),
                    "updated_at": _now(),
                }
            )
            review = load_review_record(attempt_id, question_no, data_root=data_root)
            updated = review.model_copy(
                update={
                    "status": AttemptReviewStatus.FEEDBACK_ADDED,
                    "assistant_feedback": feedback,
                    "user_resolution": UserResolution(),
                    "updated_at": _now(),
                }
            )
            save_review_record(updated, data_root=data_root)
            updated_reviews.append(updated)
    return updated_reviews


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def workbench_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LEET Attempt Review</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #f7f7f4; color: #202124; }
    header { height: 48px; display: flex; align-items: center; gap: 14px; padding: 0 16px; background: #263238; color: #fff; }
    main { display: grid; grid-template-columns: 280px minmax(340px, 1fr) 420px; height: calc(100vh - 48px); }
    aside, section { min-width: 0; overflow: auto; }
    aside { border-right: 1px solid #d7d7d2; background: #fff; }
    .queue-item { width: 100%; text-align: left; border: 0; border-bottom: 1px solid #eee; border-radius: 0; padding: 10px; background: #fff; cursor: pointer; }
    .queue-item.active { background: #e8f0ef; }
    .queue-item strong { display: block; }
    .queue-item span { color: #5f6368; font-size: 12px; }
    .question { padding: 16px; }
    .choice { padding: 8px 0; border-bottom: 1px solid #e6e6e2; }
    .choice strong { display: inline-block; width: 28px; }
    .pill { display: inline-block; min-width: 24px; text-align: center; border-radius: 999px; padding: 2px 8px; margin-left: 6px; font-size: 12px; background: #e8eaed; }
    .pill.bad { background: #fce8e6; color: #b3261e; }
    .pill.good { background: #e6f4ea; color: #137333; }
    .editor { border-left: 1px solid #d7d7d2; background: #fff; padding: 14px; }
    label { display: block; font-size: 12px; color: #5f6368; margin: 10px 0 4px; }
    textarea, input, select, button { font: inherit; }
    textarea, input, select { width: 100%; padding: 7px; border: 1px solid #c4c7c5; border-radius: 6px; }
    textarea { min-height: 78px; resize: vertical; }
    button { border: 1px solid #9aa0a6; background: #fff; border-radius: 6px; padding: 7px 10px; cursor: pointer; }
    .actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
    .feedback { background: #f8fafd; border: 1px solid #d3e3fd; border-radius: 6px; padding: 10px; margin-top: 12px; }
    .muted { color: #5f6368; }
    pre { white-space: pre-wrap; background: #f1f3f4; padding: 8px; border-radius: 6px; max-height: 180px; overflow: auto; }
  </style>
</head>
<body>
  <header><strong>LEET Attempt Review</strong><span id="summary"></span></header>
  <main>
    <aside id="queue"></aside>
    <section class="question">
      <h2 id="questionTitle"></h2>
      <div id="grading"></div>
      <h3>Question</h3>
      <p id="stem" class="muted"></p>
      <div id="choices"></div>
    </section>
    <section class="editor">
      <label>Status</label><select id="status">
        <option value="user_entered">user_entered</option>
        <option value="ready_for_feedback">ready_for_feedback</option>
      </select>
      <label>Reasoning text</label><textarea id="reasoning_text"></textarea>
      <label>Why selected</label><textarea id="why_selected"></textarea>
      <label>Decisive condition, phrase, or step</label><textarea id="decisive_condition"></textarea>
      <label>Why rejected or missed correct choice</label><textarea id="why_rejected_correct"></textarea>
      <label>Current reflection</label><textarea id="current_reflection"></textarea>
      <label>Time pressure / confidence / condition notes</label><textarea id="condition_notes"></textarea>
      <div class="actions"><button id="save">Save</button><button id="next">Next</button></div>
      <div class="feedback" id="feedback"></div>
      <label>Resolution</label><select id="resolution_status">
        <option value="pending">pending</option>
        <option value="accepted">accepted</option>
        <option value="edited">edited</option>
        <option value="rejected">rejected</option>
      </select>
      <label>Final error tags, comma separated</label><input id="final_error_tags">
      <label>Resolution note</label><textarea id="resolution_note"></textarea>
      <div class="actions"><button id="saveResolution">Save resolution</button></div>
    </section>
  </main>
  <script>
    let state, current, autosaveTimer;
    const fields = ["reasoning_text", "why_selected", "decisive_condition", "why_rejected_correct", "current_reflection", "condition_notes"];
    async function load() {
      state = await fetch("/api/state").then(r => r.json());
      document.getElementById("summary").textContent = `${state.attempt.id} - ${state.score}/${state.total}`;
      renderQueue();
      select(current?.question_no || state.reviews[0]?.question_no);
    }
    function renderQueue() {
      const queue = document.getElementById("queue"); queue.innerHTML = "";
      state.reviews.forEach(review => {
        const button = document.createElement("button"); button.className = "queue-item" + (current?.question_no === review.question_no ? " active" : "");
        const title = document.createElement("strong"); title.textContent = `Q${String(review.question_no).padStart(3, "0")}`;
        const meta = document.createElement("span"); meta.textContent = `${review.status} - chose ${review.grading.selected_choice}, correct ${review.grading.correct_choice}`;
        button.append(title, meta);
        button.onclick = () => select(review.question_no);
        queue.appendChild(button);
      });
    }
    function choiceText(choice) {
      if (typeof choice === "string") return choice;
      if (choice && typeof choice === "object") return choice.text || choice.body || "";
      return "";
    }
    function choiceNumber(choice, index) {
      if (choice && typeof choice === "object" && choice.choice_no) return choice.choice_no;
      return index + 1;
    }
    function select(questionNo) {
      current = state.reviews.find(review => review.question_no === questionNo);
      if (!current) return;
      renderQueue();
      const question = state.questions[String(questionNo)] || state.questions[questionNo] || {};
      document.getElementById("questionTitle").textContent = `Question ${questionNo}`;
      document.getElementById("grading").innerHTML = `Selected <span class="pill bad">${current.grading.selected_choice}</span> Correct <span class="pill good">${current.grading.correct_choice}</span>`;
      document.getElementById("stem").textContent = question.stem || "No verified question text available.";
      const choices = document.getElementById("choices"); choices.innerHTML = "";
      (question.choices || []).forEach((choice, index) => {
        const div = document.createElement("div"); div.className = "choice";
        div.innerHTML = `<strong>${choiceNumber(choice, index)}</strong>${choiceText(choice)}`;
        choices.appendChild(div);
      });
      document.getElementById("status").value = current.status === "ready_for_feedback" ? "ready_for_feedback" : "user_entered";
      fields.forEach(id => document.getElementById(id).value = current.user_self_review[id] || "");
      renderFeedback();
    }
    function renderFeedback() {
      const box = document.getElementById("feedback");
      const feedback = current.assistant_feedback;
      if (!feedback) {
        box.innerHTML = '<strong>Assistant feedback</strong><p class="muted">No feedback imported yet.</p>';
      } else {
        const tags = (feedback.provisional_error_tags || []).join(", ") || "none";
        box.innerHTML = `<strong>Assistant feedback</strong><p>${feedback.diagnosis_text || ""}</p><p><b>Provisional tags:</b> ${tags}</p><p><b>Correction rule:</b> ${feedback.correction_rule || ""}</p>`;
      }
      const resolution = current.user_resolution || {};
      document.getElementById("resolution_status").value = resolution.status || "pending";
      document.getElementById("final_error_tags").value = (resolution.final_error_tags || []).join(", ");
      document.getElementById("resolution_note").value = resolution.note || "";
    }
    async function save() {
      if (!current) return;
      const body = {status: document.getElementById("status").value};
      fields.forEach(id => body[id] = document.getElementById(id).value);
      const response = await fetch(`/api/reviews/${current.question_no}/self-review`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (!response.ok) return;
      await load();
    }
    async function saveResolution() {
      if (!current) return;
      const body = {
        status: document.getElementById("resolution_status").value,
        final_error_tags: document.getElementById("final_error_tags").value.split(",").map(s => s.trim()).filter(Boolean),
        note: document.getElementById("resolution_note").value || null
      };
      const response = await fetch(`/api/reviews/${current.question_no}/resolution`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (!response.ok) return;
      await load();
    }
    function scheduleAutosave() {
      clearTimeout(autosaveTimer);
      autosaveTimer = setTimeout(save, 800);
    }
    fields.concat(["status"]).forEach(id => document.getElementById(id).addEventListener("input", scheduleAutosave));
    document.getElementById("save").onclick = save;
    document.getElementById("saveResolution").onclick = saveResolution;
    document.getElementById("next").onclick = () => {
      const index = state.reviews.findIndex(review => review.question_no === current?.question_no);
      select(state.reviews[(index + 1) % state.reviews.length]?.question_no);
    };
    load();
  </script>
</body>
</html>"""


class AttemptReviewWorkbench:
    """Local HTTP workbench for attempt self-review."""

    def __init__(self, attempt_id: str, *, data_root: Path = Path("data")) -> None:
        self.attempt_id = attempt_id
        self.data_root = data_root

    def state_payload(self) -> dict[str, Any]:
        state = initialize_attempt_reviews(self.attempt_id, data_root=self.data_root)
        return state.model_dump(mode="json")

    def handler_class(self) -> type[BaseHTTPRequestHandler]:
        workbench = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                try:
                    if parsed.path == "/":
                        _text_response(self, workbench_html())
                        return
                    if parsed.path == "/api/state":
                        _json_response(self, workbench.state_payload())
                        return
                except AttemptReviewError as exc:
                    _json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                _json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if not parsed.path.startswith("/api/reviews/"):
                    _json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                suffix = parsed.path.removeprefix("/api/reviews/")
                parts = suffix.split("/")
                if len(parts) != 2:
                    _json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                try:
                    question_no = _question_no_from_value(unquote(parts[0]))
                    length = int(self.headers.get("Content-Length") or 0)
                    body = self.rfile.read(length).decode("utf-8")
                    payload = json.loads(body) if body else {}
                    if parts[1] == "self-review":
                        review = update_user_self_review(
                            workbench.attempt_id,
                            question_no,
                            payload,
                            data_root=workbench.data_root,
                        )
                    elif parts[1] == "resolution":
                        review = update_user_resolution(
                            workbench.attempt_id,
                            question_no,
                            payload,
                            data_root=workbench.data_root,
                        )
                    else:
                        _json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
                        return
                except (json.JSONDecodeError, ValueError, ValidationError, AttemptReviewError) as exc:
                    _json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                _json_response(self, review.model_dump(mode="json"))

        return Handler


def create_review_server(
    attempt_id: str,
    *,
    data_root: Path = Path("data"),
    host: str = "127.0.0.1",
    port: int = 8766,
) -> ThreadingHTTPServer:
    workbench = AttemptReviewWorkbench(attempt_id, data_root=data_root)
    return ThreadingHTTPServer((host, port), workbench.handler_class())


def serve_review_workbench(
    attempt_id: str,
    *,
    data_root: Path = Path("data"),
    host: str = "127.0.0.1",
    port: int = 8766,
    open_browser: bool = True,
) -> str:
    server = create_review_server(attempt_id, data_root=data_root, host=host, port=port)
    url = f"http://{server.server_address[0]}:{server.server_address[1]}/"
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return url
