"""Persistence and aggregation for retry-PDF solving outcomes."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence


DEFAULT_DATA_ROOT = Path("data")
SCHEMA_VERSION = 1
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RetryResultError(RuntimeError):
    """Raised when retry-session results are invalid or cannot be persisted."""


class RetryOutcome(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RetryResultItem:
    review_file: str
    question_id: str | None
    year: int | None
    section: str | None
    question_no: int
    selected_choice: int | None
    correct_choice: int
    outcome: RetryOutcome
    answered_at: str
    note: str | None = None


@dataclass(frozen=True)
class RetrySessionResult:
    schema_version: int
    session_id: str
    manifest_path: str
    title: str
    created_at: str
    updated_at: str
    items: tuple[RetryResultItem, ...]


@dataclass(frozen=True)
class RetryQuestionStatus:
    review_file: str
    latest_outcome: RetryOutcome
    attempt_count: int
    session_count: int
    last_selected_choice: int | None
    correct_choice: int
    last_answered_at: str
    last_session_id: str


def retry_attempts_dir(*, data_root: Path = DEFAULT_DATA_ROOT) -> Path:
    return Path(data_root) / "retry_attempts"


def _validate_session_id(value: Any) -> str:
    session_id = str(value or "").strip()
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise RetryResultError(
            "session_id must use only letters, digits, dots, underscores, or hyphens and be at most 128 characters"
        )
    return session_id


def retry_result_path(session_id: str, *, data_root: Path = DEFAULT_DATA_ROOT) -> Path:
    safe_id = _validate_session_id(session_id)
    return retry_attempts_dir(data_root=data_root) / f"{safe_id}.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RetryResultError(f"File not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RetryResultError(f"Could not read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RetryResultError(f"Expected a JSON object: {path}")
    return payload


def _normalized_review_file(value: Any) -> str:
    review_file = str(value or "").strip().replace("\\", "/")
    if not review_file or review_file.startswith("/") or ".." in Path(review_file).parts:
        raise RetryResultError(f"Invalid review_file: {value!r}")
    return review_file


def load_retry_manifest(manifest_path: Path) -> dict[str, Any]:
    """Load and validate the subset of a retry manifest needed for grading."""

    path = Path(manifest_path)
    payload = _read_json(path)
    session_id = _validate_session_id(payload.get("session_id") or path.stem)
    selected = payload.get("selected")
    if not isinstance(selected, list) or not selected:
        raise RetryResultError("Retry manifest must contain a non-empty selected list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(selected, start=1):
        if not isinstance(raw, dict):
            raise RetryResultError(f"Manifest selected item {index} must be an object")
        review_file = _normalized_review_file(raw.get("review_file"))
        if review_file in seen:
            raise RetryResultError(f"Manifest contains duplicate review_file: {review_file}")
        seen.add(review_file)
        try:
            question_no = int(raw["question_no"])
            correct_choice = int(raw["correct_choice"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RetryResultError(f"Manifest item {review_file} has invalid question metadata") from exc
        if question_no < 1 or not 1 <= correct_choice <= 5:
            raise RetryResultError(f"Manifest item {review_file} has out-of-range question metadata")
        year_raw = raw.get("year")
        try:
            year = int(year_raw) if year_raw is not None else None
        except (TypeError, ValueError) as exc:
            raise RetryResultError(f"Manifest item {review_file} has invalid year") from exc
        normalized.append(
            {
                "review_file": review_file,
                "question_id": str(raw["question_id"]) if raw.get("question_id") else None,
                "year": year,
                "section": str(raw["section"]) if raw.get("section") else None,
                "question_no": question_no,
                "correct_choice": correct_choice,
            }
        )
    return {
        "session_id": session_id,
        "title": str(payload.get("title") or "LEET 오답 재풀이"),
        "selected": normalized,
        "manifest_path": path,
    }


def _stored_manifest_path(path: Path, *, data_root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(data_root).resolve().parent).as_posix()
    except ValueError:
        return resolved.as_posix()


def _parse_choice(value: Any, *, review_file: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise RetryResultError(f"selected_choice for {review_file} must be 1-5 or blank")
    try:
        choice = int(value)
    except (TypeError, ValueError) as exc:
        raise RetryResultError(f"selected_choice for {review_file} must be 1-5 or blank") from exc
    if not 1 <= choice <= 5:
        raise RetryResultError(f"selected_choice for {review_file} must be 1-5 or blank")
    return choice


def _normalized_answers(answers: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for raw in answers:
        if not isinstance(raw, Mapping):
            raise RetryResultError("Each answer must be an object")
        review_file = _normalized_review_file(raw.get("review_file"))
        if review_file in normalized:
            raise RetryResultError(f"Duplicate answer for {review_file}")
        note_raw = raw.get("note")
        if note_raw is not None and not isinstance(note_raw, str):
            raise RetryResultError(f"note for {review_file} must be a string")
        note = note_raw.strip() if isinstance(note_raw, str) else None
        if note and len(note) > 2000:
            raise RetryResultError(f"note for {review_file} must not exceed 2000 characters")
        normalized[review_file] = {
            "selected_choice": _parse_choice(raw.get("selected_choice"), review_file=review_file),
            "note": note or None,
        }
    return normalized


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RetryResultError(f"Could not write retry result {path}: {exc}") from exc


def save_retry_session_result(
    manifest_path: Path,
    answers: Sequence[Mapping[str, Any]],
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> RetrySessionResult:
    """Grade and persist one complete retry session from an immutable manifest."""

    data_root = Path(data_root)
    manifest = load_retry_manifest(Path(manifest_path))
    submitted = _normalized_answers(answers)
    expected = {item["review_file"] for item in manifest["selected"]}
    if set(submitted) != expected:
        missing = sorted(expected - set(submitted))
        unknown = sorted(set(submitted) - expected)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown: {', '.join(unknown)}")
        raise RetryResultError("Answers must match every manifest item (" + "; ".join(details) + ")")

    now = datetime.now(timezone.utc).isoformat()
    path = retry_result_path(manifest["session_id"], data_root=data_root)
    created_at = now
    if path.is_file():
        previous = load_retry_session_result(path)
        created_at = previous.created_at
    items: list[RetryResultItem] = []
    for item in manifest["selected"]:
        answer = submitted[item["review_file"]]
        selected_choice = answer["selected_choice"]
        outcome = (
            RetryOutcome.SKIPPED
            if selected_choice is None
            else RetryOutcome.CORRECT
            if selected_choice == item["correct_choice"]
            else RetryOutcome.INCORRECT
        )
        items.append(
            RetryResultItem(
                review_file=item["review_file"],
                question_id=item["question_id"],
                year=item["year"],
                section=item["section"],
                question_no=item["question_no"],
                selected_choice=selected_choice,
                correct_choice=item["correct_choice"],
                outcome=outcome,
                answered_at=now,
                note=answer["note"],
            )
        )
    result = RetrySessionResult(
        schema_version=SCHEMA_VERSION,
        session_id=manifest["session_id"],
        manifest_path=_stored_manifest_path(manifest["manifest_path"], data_root=data_root),
        title=manifest["title"],
        created_at=created_at,
        updated_at=now,
        items=tuple(items),
    )
    payload = asdict(result)
    for item in payload["items"]:
        item["outcome"] = str(item["outcome"])
    _write_json_atomic(path, payload)
    return result


def load_retry_session_result(path: Path) -> RetrySessionResult:
    payload = _read_json(Path(path))
    try:
        session_id = _validate_session_id(payload["session_id"])
        schema_version = int(payload["schema_version"])
        manifest_path = str(payload["manifest_path"])
        title = str(payload.get("title") or "LEET 오답 재풀이")
        created_at = str(payload["created_at"])
        updated_at = str(payload["updated_at"])
        raw_items = payload["items"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RetryResultError(f"Invalid retry result header in {path}") from exc
    if schema_version != SCHEMA_VERSION or not isinstance(raw_items, list):
        raise RetryResultError(f"Unsupported retry result schema in {path}")
    items: list[RetryResultItem] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise RetryResultError(f"Invalid retry result item in {path}")
        try:
            review_file = _normalized_review_file(raw["review_file"])
            outcome = RetryOutcome(str(raw["outcome"]))
            question_no = int(raw["question_no"])
            correct_choice = int(raw["correct_choice"])
            selected_choice = _parse_choice(raw.get("selected_choice"), review_file=review_file)
            year = int(raw["year"]) if raw.get("year") is not None else None
        except (KeyError, TypeError, ValueError, RetryResultError) as exc:
            raise RetryResultError(f"Invalid retry result item in {path}: {exc}") from exc
        if review_file in seen or question_no < 1 or not 1 <= correct_choice <= 5:
            raise RetryResultError(f"Duplicate or out-of-range retry result item in {path}")
        if outcome is RetryOutcome.SKIPPED and selected_choice is not None:
            raise RetryResultError(f"Skipped item must have a blank choice in {path}")
        if outcome is not RetryOutcome.SKIPPED and selected_choice is None:
            raise RetryResultError(f"Graded item must have a selected choice in {path}")
        expected_outcome = (
            RetryOutcome.SKIPPED
            if selected_choice is None
            else RetryOutcome.CORRECT
            if selected_choice == correct_choice
            else RetryOutcome.INCORRECT
        )
        if outcome is not expected_outcome:
            raise RetryResultError(f"Stored outcome does not match choices in {path}")
        seen.add(review_file)
        items.append(
            RetryResultItem(
                review_file=review_file,
                question_id=str(raw["question_id"]) if raw.get("question_id") else None,
                year=year,
                section=str(raw["section"]) if raw.get("section") else None,
                question_no=question_no,
                selected_choice=selected_choice,
                correct_choice=correct_choice,
                outcome=outcome,
                answered_at=str(raw["answered_at"]),
                note=str(raw["note"]) if raw.get("note") else None,
            )
        )
    return RetrySessionResult(
        schema_version=schema_version,
        session_id=session_id,
        manifest_path=manifest_path,
        title=title,
        created_at=created_at,
        updated_at=updated_at,
        items=tuple(items),
    )


def load_latest_retry_statuses(
    *, data_root: Path = DEFAULT_DATA_ROOT
) -> dict[str, RetryQuestionStatus]:
    """Aggregate latest result and counts for every retried review file."""

    directory = retry_attempts_dir(data_root=data_root)
    if not directory.is_dir():
        return {}
    aggregates: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        session = load_retry_session_result(path)
        for item in session.items:
            current = aggregates.setdefault(
                item.review_file,
                {"attempt_count": 0, "session_count": 0, "latest_key": ("", "")},
            )
            current["session_count"] += 1
            if item.selected_choice is not None:
                current["attempt_count"] += 1
            key = (item.answered_at, session.session_id)
            if key >= current["latest_key"]:
                current.update(
                    {
                        "latest_key": key,
                        "latest_outcome": item.outcome,
                        "last_selected_choice": item.selected_choice,
                        "correct_choice": item.correct_choice,
                        "last_answered_at": item.answered_at,
                        "last_session_id": session.session_id,
                    }
                )
    return {
        review_file: RetryQuestionStatus(
            review_file=review_file,
            latest_outcome=value["latest_outcome"],
            attempt_count=value["attempt_count"],
            session_count=value["session_count"],
            last_selected_choice=value["last_selected_choice"],
            correct_choice=value["correct_choice"],
            last_answered_at=value["last_answered_at"],
            last_session_id=value["last_session_id"],
        )
        for review_file, value in aggregates.items()
    }


def retry_status_payload(status: RetryQuestionStatus) -> dict[str, Any]:
    payload = asdict(status)
    payload["latest_outcome"] = str(status.latest_outcome)
    return payload
