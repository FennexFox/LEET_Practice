from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import build_tagging_dashboard as dashboard


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 64 * 1024
MAX_RETRY_QUESTIONS = 100
MAX_RECENT_RETRY_SESSIONS = 50
OUTPUT_ROOT = (dashboard.ROOT / "output").resolve()
RETRY_OUTPUT_ROOT = (OUTPUT_ROOT / "pdf" / "retry-pdfs").resolve()
RETRY_RESULTS_LOCK = threading.Lock()
RETRY_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RETRY_SHORT_CODE_PATTERN = re.compile(r"^[0-9a-fA-F]{10}$")
LANGUAGE_SECTION = "\uc5b8\uc5b4\uc774\ud574"
REASONING_SECTION = "\ucd94\ub9ac\ub17c\uc99d"
SECTION_ALIASES = {
    LANGUAGE_SECTION: [LANGUAGE_SECTION, "\uc5b8\uc5b4"],
    REASONING_SECTION: [REASONING_SECTION, "\ucd94\ub9ac"],
}


class TaggingDashboardHandler(BaseHTTPRequestHandler):
    server_version = "LEETTaggingDashboard/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/tagging-dashboard", "/docs/tagging-dashboard.html"}:
            self._send_dashboard_html()
            return
        if path == "/review":
            self._send_review_html()
            return
        if path == "/retry-results":
            self._send_retry_results_html()
            return
        if path == "/api/dashboard":
            self._send_dashboard_json()
            return
        if path == "/api/retry-statuses":
            self._send_retry_statuses_json()
            return
        if path == "/api/retry-sessions":
            self._send_retry_sessions_json()
            return
        if path == "/healthz":
            self._send_json({"ok": True})
            return
        if path == "/download":
            self._send_download()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/retry-pdf", "/api/retry-results"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            payload = self._read_json_request()
            response = (
                create_retry_pdf_response(payload)
                if path == "/api/retry-pdf"
                else save_retry_result_response(payload)
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_error(exc, wants_json=True, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            if path == "/api/retry-results" and isinstance(exc, _load_retry_result_api()["error"]):
                self._send_error(exc, wants_json=True, status=HTTPStatus.BAD_REQUEST)
                return
            retry_error = retry_pdf_error_type()
            status = HTTPStatus.UNPROCESSABLE_ENTITY if isinstance(exc, retry_error) else HTTPStatus.INTERNAL_SERVER_ERROR
            self._send_error(exc, wants_json=True, status=status)
            return
        self._send_json(response, status=HTTPStatus.CREATED)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send_dashboard_html(self) -> None:
        try:
            output = dashboard.build_current_dashboard_html()
            dashboard.validate_html(output)
        except Exception as exc:
            self._send_error(exc, wants_json=False)
            return
        self._send_bytes(output.encode("utf-8"), "text/html; charset=utf-8")

    def _send_review_html(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        review_file = (query.get("file") or [""])[0]
        try:
            output = build_review_page(review_file)
        except Exception as exc:
            self._send_error(exc, wants_json=False)
            return
        self._send_bytes(output.encode("utf-8"), "text/html; charset=utf-8")

    def _send_retry_results_html(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        manifest = (query.get("manifest") or [""])[0]
        session = (query.get("session") or [""])[0]
        try:
            if manifest and session:
                raise ValueError("Provide either manifest or session, not both")
            manifest_reference: str | Path = (
                resolve_retry_session_manifest(session) if session else manifest
            )
            output = build_retry_results_page(manifest_reference)
        except ValueError as exc:
            self._send_error(exc, wants_json=False, status=HTTPStatus.BAD_REQUEST)
            return
        except FileNotFoundError as exc:
            self._send_error(exc, wants_json=False, status=HTTPStatus.NOT_FOUND)
            return
        except Exception as exc:
            self._send_error(exc, wants_json=False)
            return
        self._send_bytes(output.encode("utf-8"), "text/html; charset=utf-8")

    def _send_dashboard_json(self) -> None:
        try:
            payload = dashboard.build_dashboard_data()
        except Exception as exc:
            self._send_error(exc, wants_json=True)
            return
        self._send_json(payload)

    def _send_retry_statuses_json(self) -> None:
        try:
            payload = retry_status_response()
        except Exception as exc:
            self._send_error(exc, wants_json=True)
            return
        self._send_json(payload)

    def _send_retry_sessions_json(self) -> None:
        try:
            payload = retry_sessions_response()
        except Exception as exc:
            self._send_error(exc, wants_json=True)
            return
        self._send_json(payload)

    def _read_json_request(self) -> object:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            raise ValueError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise ValueError(f"JSON body must be between 1 and {MAX_REQUEST_BYTES} bytes")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_download(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        requested = (query.get("file") or [""])[0]
        try:
            path = resolve_output_file(requested, must_exist=True)
        except ValueError as exc:
            self._send_error(exc, wants_json=False, status=HTTPStatus.BAD_REQUEST)
            return
        except FileNotFoundError as exc:
            self._send_error(exc, wants_json=False, status=HTTPStatus.NOT_FOUND)
            return
        content_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/json; charset=utf-8"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(path.name)}")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status=status)

    def _send_error(
        self,
        exc: Exception,
        wants_json: bool,
        status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> None:
        if wants_json:
            self._send_json(
                {"error": type(exc).__name__, "message": str(exc)},
                status=status,
            )
            return
        body = (
            "<!doctype html><meta charset=\"utf-8\">"
            "<title>Dashboard error</title>"
            "<h1>Dashboard error</h1>"
            f"<pre>{type(exc).__name__}: {dashboard.h(str(exc))}</pre>"
        ).encode("utf-8")
        self._send_bytes(body, "text/html; charset=utf-8", status=status)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _load_retry_pdf_api() -> tuple[Any, type[Exception]]:
    try:
        from leet_practice.retry_pdf import RetryPdfError, create_retry_pdf_bundle
    except ModuleNotFoundError:
        src_dir = dashboard.ROOT / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        from leet_practice.retry_pdf import RetryPdfError, create_retry_pdf_bundle
    return create_retry_pdf_bundle, RetryPdfError


def _load_retry_result_api() -> dict[str, Any]:
    try:
        from leet_practice.retry_results import (
            RetryResultError,
            load_latest_retry_statuses,
            load_retry_manifest,
            load_retry_session_result,
            retry_result_path,
            retry_status_payload,
            save_retry_session_result,
        )
    except ModuleNotFoundError:
        src_dir = dashboard.ROOT / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        from leet_practice.retry_results import (
            RetryResultError,
            load_latest_retry_statuses,
            load_retry_manifest,
            load_retry_session_result,
            retry_result_path,
            retry_status_payload,
            save_retry_session_result,
        )
    return {
        "error": RetryResultError,
        "load_statuses": load_latest_retry_statuses,
        "load_manifest": load_retry_manifest,
        "load_result": load_retry_session_result,
        "result_path": retry_result_path,
        "status_payload": retry_status_payload,
        "save": save_retry_session_result,
    }


def retry_pdf_error_type() -> type[Exception]:
    try:
        return _load_retry_pdf_api()[1]
    except (ImportError, ModuleNotFoundError):
        return RuntimeError


def _validate_string_list(
    payload: dict[str, Any],
    field: str,
    allowed: set[str],
) -> list[str] | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field} must be a list of strings")
    normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise ValueError(f"Unknown {field}: {', '.join(unknown)}")
    return normalized or None


def validate_retry_pdf_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("JSON body must be an object")
    allowed_fields = {
        "review_files",
        "limit",
        "tags",
        "years",
        "sections",
        "include_holdout",
        "include_completed",
        "title",
    }
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise ValueError(f"Unknown fields: {', '.join(unknown_fields)}")

    records = dashboard.load_records()
    records_by_file = {
        str(record.get("review_file") or "").replace("\\", "/"): record
        for record in records
    }
    raw_review_files = payload.get("review_files")
    review_files: list[str] | None
    if raw_review_files is None:
        review_files = None
    else:
        if not isinstance(raw_review_files, list) or any(not isinstance(item, str) for item in raw_review_files):
            raise TypeError("review_files must be a list of strings")
        review_files = list(
            dict.fromkeys(item.strip().replace("\\", "/") for item in raw_review_files if item.strip())
        )
        if not review_files:
            raise ValueError("review_files cannot be empty")
        unknown_files = [item for item in review_files if item not in records_by_file]
        if unknown_files:
            raise ValueError(f"Unknown review_file: {unknown_files[0]}")

    limit = payload.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if not 1 <= limit <= MAX_RETRY_QUESTIONS:
        raise ValueError(f"limit must be between 1 and {MAX_RETRY_QUESTIONS}")

    include_holdout = payload.get("include_holdout", False)
    if not isinstance(include_holdout, bool):
        raise TypeError("include_holdout must be a boolean")
    if review_files and not include_holdout:
        selected_holdouts = [item for item in review_files if records_by_file[item].get("holdout")]
        if selected_holdouts:
            raise ValueError("A holdout record was selected without include_holdout=true")

    include_completed = payload.get("include_completed", False)
    if not isinstance(include_completed, bool):
        raise TypeError("include_completed must be a boolean")

    title = payload.get("title", "LEET 오답 재풀이")
    if not isinstance(title, str):
        raise TypeError("title must be a string")
    title = title.strip()
    if not title or len(title) > 160:
        raise ValueError("title must contain between 1 and 160 characters")

    known_tags = {
        tag
        for record in records
        for tag in [record["provisional_tags"]["primary"]]
        + list(record["provisional_tags"].get("secondary") or [])
    }
    tags = _validate_string_list(payload, "tags", known_tags)
    sections = _validate_string_list(
        payload,
        "sections",
        {str(record["section"]) for record in records if record.get("section")},
    )
    raw_years = payload.get("years")
    years: list[int] | None
    if raw_years is None:
        years = None
    else:
        if not isinstance(raw_years, list) or any(isinstance(item, bool) or not isinstance(item, int) for item in raw_years):
            raise TypeError("years must be a list of integers")
        years = list(dict.fromkeys(raw_years)) or None
        allowed_years = {int(record["year"]) for record in records if record.get("year") is not None}
        unknown_years = sorted(set(years or []) - allowed_years)
        if unknown_years:
            raise ValueError(f"Unknown years: {', '.join(map(str, unknown_years))}")

    return {
        "review_files": review_files,
        "limit": limit,
        "tags": tags,
        "years": years,
        "sections": sections,
        "include_holdout": include_holdout,
        "include_completed": include_completed,
        "title": title,
    }


def resolve_output_file(value: str | Path, *, must_exist: bool) -> Path:
    if not value:
        raise ValueError("Missing output file")
    supplied = Path(value)
    path = supplied.resolve() if supplied.is_absolute() else (dashboard.ROOT / supplied).resolve()
    if not path.is_relative_to(OUTPUT_ROOT):
        raise ValueError("Download must be under the repository output directory")
    if path.suffix.lower() not in {".pdf", ".json"}:
        raise ValueError("Only generated PDF and JSON files can be downloaded")
    if must_exist and not path.is_file():
        raise FileNotFoundError(str(value))
    return path


def _json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _output_reference(path_value: str | Path) -> tuple[str, str]:
    path = resolve_output_file(path_value, must_exist=True)
    relative = path.relative_to(dashboard.ROOT).as_posix()
    return relative, f"/download?file={quote(relative)}"


def resolve_retry_manifest(value: str | Path, *, must_exist: bool) -> Path:
    path = resolve_output_file(value, must_exist=must_exist)
    if not path.is_relative_to(RETRY_OUTPUT_ROOT) or path.suffix.lower() != ".json":
        raise ValueError("Retry manifest must be a JSON file under output/pdf/retry-pdfs")
    return path


def _retry_manifest_generated_at(payload: dict[str, Any], path: Path) -> tuple[str, float]:
    value = payload.get("generated_at")
    if isinstance(value, str) and value.strip():
        generated_at = value.strip()
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return generated_at, parsed.timestamp()
        except ValueError:
            pass
    modified = path.stat().st_mtime
    return datetime.fromtimestamp(modified, timezone.utc).isoformat(), modified


def _retry_session_records() -> list[dict[str, Any]]:
    """Return validated local session metadata, newest first.

    The internal manifest path and sort key are retained for server-side
    resolution, but callers must project records before returning JSON.
    """

    if not RETRY_OUTPUT_ROOT.is_dir():
        return []
    api = _load_retry_result_api()
    records: list[dict[str, Any]] = []
    for candidate_path in RETRY_OUTPUT_ROOT.glob("*.json"):
        try:
            manifest_path = candidate_path.resolve()
            if not manifest_path.is_relative_to(RETRY_OUTPUT_ROOT) or manifest_path.suffix.lower() != ".json":
                continue
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            manifest = api["load_manifest"](manifest_path)
            generated_at, sort_timestamp = _retry_manifest_generated_at(raw, manifest_path)
        except (OSError, json.JSONDecodeError, ValueError, TypeError, api["error"]):
            continue

        result_status = "not_submitted"
        answered_count = 0
        correct_count = 0
        updated_at = None
        try:
            result_path = api["result_path"](
                manifest["session_id"],
                data_root=dashboard.ROOT / "data",
            )
            if result_path.is_file():
                result = api["load_result"](result_path)
                result_status = "submitted"
                answered_count = sum(
                    1 for item in result.items if item.selected_choice is not None
                )
                correct_count = sum(
                    1 for item in result.items if str(item.outcome) == "correct"
                )
                updated_at = result.updated_at
        except (OSError, ValueError, TypeError, api["error"]):
            result_status = "invalid"

        session_id = manifest["session_id"]
        records.append(
            {
                "session_id": session_id,
                "short_code": session_id[-10:] if RETRY_SHORT_CODE_PATTERN.fullmatch(session_id[-10:]) else None,
                "generated_at": generated_at,
                "title": manifest["title"],
                "question_count": len(manifest["selected"]),
                "result_status": result_status,
                "answered_count": answered_count,
                "correct_count": correct_count,
                "updated_at": updated_at,
                "result_entry_url": f"/retry-results?session={quote(session_id)}",
                "_manifest_path": manifest_path,
                "_sort_timestamp": sort_timestamp,
            }
        )
    records.sort(key=lambda record: (-record["_sort_timestamp"], record["session_id"]))
    return records


def discover_retry_sessions(*, limit: int = MAX_RECENT_RETRY_SESSIONS) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    public_fields = (
        "session_id",
        "short_code",
        "generated_at",
        "title",
        "question_count",
        "result_status",
        "answered_count",
        "correct_count",
        "updated_at",
        "result_entry_url",
    )
    return [
        {field: record[field] for field in public_fields}
        for record in _retry_session_records()[:limit]
    ]


def resolve_retry_session_manifest(value: str) -> Path:
    session_reference = str(value or "").strip()
    if not session_reference:
        raise ValueError("Missing retry session ID or short code")
    if not RETRY_SESSION_ID_PATTERN.fullmatch(session_reference):
        raise ValueError("Enter a full session ID or its final 10 hexadecimal characters")

    records = _retry_session_records()
    exact = [record for record in records if record["session_id"] == session_reference]
    if len(exact) == 1:
        return exact[0]["_manifest_path"]
    if len(exact) > 1:
        raise ValueError("Multiple manifests use that session ID; remove the duplicate or use its manifest URL")

    if not RETRY_SHORT_CODE_PATTERN.fullmatch(session_reference):
        raise FileNotFoundError(f"Retry session not found: {session_reference}")
    normalized = session_reference.lower()
    matches = [
        record
        for record in records
        if record["session_id"].lower().endswith(normalized)
    ]
    if not matches:
        raise FileNotFoundError(f"Retry session not found: {session_reference}")
    if len(matches) > 1:
        raise ValueError("That short code is ambiguous; enter the full session ID")
    return matches[0]["_manifest_path"]


def next_retry_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return OUTPUT_ROOT / "pdf" / "retry-pdfs" / f"retry-{stamp}.pdf"


def create_retry_pdf_response(payload: object) -> dict[str, Any]:
    options = validate_retry_pdf_payload(payload)
    create_retry_pdf_bundle, _ = _load_retry_pdf_api()
    bundle = create_retry_pdf_bundle(
        data_root=dashboard.ROOT / "data",
        review_files=options["review_files"],
        limit=options["limit"],
        tags=options["tags"],
        years=options["years"],
        sections=options["sections"],
        include_holdout=options["include_holdout"],
        include_completed=options["include_completed"],
        title=options["title"],
        output_path=next_retry_output_path(),
        font_path=None,
    )
    pdf_path, pdf_url = _output_reference(bundle.pdf_path)
    manifest_path, manifest_url = _output_reference(bundle.manifest_path)
    skipped = _json_safe(bundle.skipped)
    return {
        "session_id": bundle.session_id,
        "pdf_path": pdf_path,
        "pdf_url": pdf_url,
        "manifest_path": manifest_path,
        "manifest_url": manifest_url,
        "result_entry_url": f"/retry-results?session={quote(bundle.session_id)}",
        "selected_count": len(bundle.selected),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


def validate_retry_result_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("JSON body must be an object")
    unknown = sorted(set(payload) - {"manifest_path", "answers"})
    if unknown:
        raise ValueError(f"Unknown fields: {', '.join(unknown)}")
    manifest_value = payload.get("manifest_path")
    if not isinstance(manifest_value, str) or not manifest_value.strip():
        raise TypeError("manifest_path must be a non-empty string")
    manifest_path = resolve_retry_manifest(manifest_value.strip(), must_exist=True)
    answers = payload.get("answers")
    if not isinstance(answers, list) or not 1 <= len(answers) <= MAX_RETRY_QUESTIONS:
        raise TypeError(f"answers must be a list with 1-{MAX_RETRY_QUESTIONS} items")
    normalized: list[dict[str, Any]] = []
    for raw in answers:
        if not isinstance(raw, dict):
            raise TypeError("Each answer must be an object")
        extra = sorted(set(raw) - {"review_file", "selected_choice", "note"})
        if extra:
            raise ValueError(f"Unknown answer fields: {', '.join(extra)}")
        review_file = raw.get("review_file")
        if not isinstance(review_file, str) or not review_file.strip():
            raise TypeError("answer review_file must be a non-empty string")
        choice = raw.get("selected_choice")
        if choice is not None and (isinstance(choice, bool) or not isinstance(choice, int) or not 1 <= choice <= 5):
            raise ValueError("selected_choice must be 1-5 or null")
        note = raw.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 2000):
            raise ValueError("note must be a string with at most 2000 characters")
        normalized.append(
            {
                "review_file": review_file.strip().replace("\\", "/"),
                "selected_choice": choice,
                "note": note.strip() if isinstance(note, str) else None,
            }
        )
    return {"manifest_path": manifest_path, "answers": normalized}


def _session_result_payload(result: Any) -> dict[str, Any]:
    items = _json_safe(result.items)
    answered = sum(1 for item in items if item["selected_choice"] is not None)
    correct = sum(1 for item in items if item["outcome"] == "correct")
    total = len(items)
    return {
        "session_id": result.session_id,
        "title": result.title,
        "created_at": result.created_at,
        "updated_at": result.updated_at,
        "total": total,
        "answered": answered,
        "correct": correct,
        "accuracy": (correct / answered) if answered else None,
        "items": items,
    }


def save_retry_result_response(payload: object) -> dict[str, Any]:
    options = validate_retry_result_payload(payload)
    api = _load_retry_result_api()
    with RETRY_RESULTS_LOCK:
        result = api["save"](
            options["manifest_path"],
            options["answers"],
            data_root=dashboard.ROOT / "data",
        )
    return _session_result_payload(result)


def retry_status_response() -> dict[str, Any]:
    api = _load_retry_result_api()
    statuses = api["load_statuses"](data_root=dashboard.ROOT / "data")
    return {
        "by_review_file": {
            review_file: api["status_payload"](status)
            for review_file, status in sorted(statuses.items())
        }
    }


def retry_sessions_response() -> dict[str, Any]:
    sessions = discover_retry_sessions()
    return {"sessions": sessions, "count": len(sessions)}


def build_retry_results_page(manifest_reference: str | Path) -> str:
    manifest_path = resolve_retry_manifest(manifest_reference, must_exist=True)
    relative_manifest = manifest_path.relative_to(dashboard.ROOT).as_posix()
    api = _load_retry_result_api()
    manifest = api["load_manifest"](manifest_path)
    result_path = api["result_path"](manifest["session_id"], data_root=dashboard.ROOT / "data")
    existing = api["load_result"](result_path) if result_path.is_file() else None
    existing_by_file = {item.review_file: item for item in existing.items} if existing else {}
    rows: list[str] = []
    for item in manifest["selected"]:
        stored = existing_by_file.get(item["review_file"])
        options = ['<option value="">건너뜀 / 미입력</option>']
        for choice in range(1, 6):
            selected = " selected" if stored and stored.selected_choice == choice else ""
            options.append(f'<option value="{choice}"{selected}>{choice}</option>')
        outcome = str(stored.outcome) if stored else "pending"
        result_text = (
            f"{outcome} - 정답 {stored.correct_choice}" if stored else "아직 제출하지 않음"
        )
        note = stored.note if stored else ""
        rows.append(
            f"""
            <tr data-review-file="{dashboard.h(item['review_file'])}">
              <td>{dashboard.h(item.get('year'))} {dashboard.h(item.get('section'))}</td>
              <td>{dashboard.h(item['question_no'])}</td>
              <td><select class="result-choice" aria-label="Q{dashboard.h(item['question_no'])} 재풀이 답">{''.join(options)}</select></td>
              <td><input class="result-note" type="text" maxlength="2000" value="{dashboard.h(note)}" placeholder="선택적 메모"></td>
              <td><span class="result-outcome {dashboard.h(outcome)}">{dashboard.h(result_text)}</span></td>
            </tr>
            """
        )
    manifest_json = json.dumps(relative_manifest, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{dashboard.h(manifest['title'])} - 재풀이 결과</title>
  <style>{dashboard.CSS}{RETRY_RESULTS_CSS}</style>
</head>
<body>
  <header class="app-header"><div class="header-inner"><div class="brand-block"><span class="brand-mark">LP</span><div><p>Retry session</p><h1>재풀이 결과 입력</h1></div></div><a class="header-action" href="/">대시보드</a></div></header>
  <main class="retry-results-main">
    <section>
      <p class="eyebrow">{dashboard.h(manifest['session_id'])}</p>
      <h2>{dashboard.h(manifest['title'])}</h2>
      <p class="result-intro">PDF를 푼 뒤 선택한 답을 입력하세요. 빈 답은 건너뜀으로 저장되어 다음 추천에 남습니다.</p>
      <form id="retryResultsForm">
        <div class="table-scroll"><table><thead><tr><th>시험</th><th>문항</th><th>재풀이 답</th><th>메모</th><th>결과</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
        <div class="result-actions"><strong id="resultSummary" aria-live="polite"></strong><button class="primary-action" type="submit">결과 저장</button></div>
      </form>
    </section>
  </main>
  <script>const retryManifestPath = {manifest_json};{RETRY_RESULTS_JS}</script>
</body>
</html>"""


RETRY_RESULTS_CSS = """
.retry-results-main { max-width: 1080px; margin: 0 auto; padding: 36px 24px 64px; }
.result-intro { color: var(--muted); }
.result-choice, .result-note { width: 100%; min-height: 38px; border: 1px solid var(--line-strong); border-radius: 8px; padding: 7px 9px; background: #fff; }
.result-note { min-width: 260px; }
.result-outcome { display: inline-flex; border-radius: 999px; padding: 4px 8px; color: var(--muted); background: #f2f4f7; white-space: nowrap; }
.result-outcome.correct { color: #047857; background: #ecfdf3; }
.result-outcome.incorrect { color: #b42318; background: #fef3f2; }
.result-outcome.skipped { color: #b54708; background: #fffaeb; }
.result-actions { display: flex; align-items: center; justify-content: flex-end; gap: 14px; margin-top: 16px; }
.result-actions button { min-height: 40px; border: 0; border-radius: 8px; padding: 8px 16px; color: #fff; background: var(--accent); font-weight: 750; cursor: pointer; }
@media (max-width: 700px) { .retry-results-main { padding: 24px 16px 48px; } .result-actions { justify-content: space-between; } }
"""


RETRY_RESULTS_JS = r"""
document.getElementById('retryResultsForm').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  const summary = document.getElementById('resultSummary');
  button.disabled = true;
  summary.textContent = '저장 중...';
  const answers = Array.from(document.querySelectorAll('tbody tr')).map(row => {
    const rawChoice = row.querySelector('.result-choice').value;
    return {
      review_file: row.dataset.reviewFile,
      selected_choice: rawChoice ? Number.parseInt(rawChoice, 10) : null,
      note: row.querySelector('.result-note').value.trim() || null
    };
  });
  try {
    const response = await fetch('/api/retry-results', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({manifest_path: retryManifestPath, answers})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || result.error || '결과 저장 실패');
    const byFile = new Map(result.items.map(item => [item.review_file, item]));
    document.querySelectorAll('tbody tr').forEach(row => {
      const item = byFile.get(row.dataset.reviewFile);
      const badge = row.querySelector('.result-outcome');
      badge.className = `result-outcome ${item.outcome}`;
      badge.textContent = `${item.outcome} - 정답 ${item.correct_choice}`;
    });
    summary.textContent = `${result.answered}/${result.total} 입력 - ${result.correct}개 정답`;
  } catch (error) {
    summary.textContent = error.message || String(error);
  } finally {
    button.disabled = false;
  }
});
"""


def resolve_review_path(review_file: str) -> Path:
    if not review_file:
        raise ValueError("Missing review file")
    root = dashboard.ROOT.resolve()
    review_root = (root / "data" / "reviews").resolve()
    path = (root / review_file).resolve()
    if not path.is_relative_to(review_root):
        raise ValueError("Review file must be under data/reviews")
    if not path.name.endswith(".review.json"):
        raise ValueError("Review file must end with .review.json")
    if not path.exists():
        raise FileNotFoundError(review_file)
    return path


def infer_year_section(review: dict[str, Any], review_path: Path) -> tuple[int | None, str | None]:
    text = " ".join(
        str(value)
        for value in [
            review.get("exam_id"),
            review.get("attempt_id"),
            review.get("question_id"),
            review_path.as_posix(),
        ]
        if value
    )
    year_match = re.search(r"\b(20\d{2})\b", text)
    section = None
    if LANGUAGE_SECTION in text:
        section = LANGUAGE_SECTION
    elif REASONING_SECTION in text:
        section = REASONING_SECTION
    return (int(year_match.group(1)) if year_match else None, section)


def load_jsonl_item(path: Path, key: str, value: Any) -> dict[str, Any] | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get(key) == value:
            return item
    return None


def load_canonical_question(review: dict[str, Any], review_path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    year, section = infer_year_section(review, review_path)
    question_no = review.get("question_no")
    if year is None or section is None or question_no is None:
        return None, None
    section_aliases = SECTION_ALIASES.get(section, [section])
    canonical_dir = next(
        (
            path
            for path in (dashboard.ROOT / "data" / "canonical").iterdir()
            if path.is_dir()
            and path.name.startswith(str(year))
            and any(alias in path.name for alias in section_aliases)
        ),
        None,
    )
    if canonical_dir is None:
        return None, None
    question = load_jsonl_item(canonical_dir / "questions.jsonl", "question_no", question_no)
    passage = None
    if question and question.get("passage_id"):
        passage = load_jsonl_item(canonical_dir / "passages.jsonl", "id", question["passage_id"])
    return question, passage


def find_tagging_record(review_file: str) -> dict[str, Any] | None:
    normalized = review_file.replace("\\", "/")
    for record in dashboard.load_records():
        if record.get("review_file") == normalized:
            return record
    return None


def build_review_page(review_file: str) -> str:
    review_path = resolve_review_path(review_file)
    relative_review_file = review_path.relative_to(dashboard.ROOT).as_posix()
    review = json.loads(review_path.read_text(encoding="utf-8"))
    question, passage = load_canonical_question(review, review_path)
    tagging_record = find_tagging_record(relative_review_file)
    grading = review.get("grading") or {}
    correct_choice = grading.get("correct_choice") or (question or {}).get("correct_answer")
    selected_choice = grading.get("selected_choice")
    title = f"{review.get('exam_id') or review.get('attempt_id') or 'Review'} Q{int(review.get('question_no') or 0):02d}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{dashboard.h(title)} - Review</title>
  <style>{dashboard.CSS}{REVIEW_CSS}</style>
</head>
<body>
  <header class="app-header">
    <h1>{dashboard.h(title)}</h1>
    <nav><a href="/">Dashboard</a><a href="/api/dashboard">API</a></nav>
  </header>
  <main class="review-main">
    <section>
      <h2>Review File</h2>
      <p><code>{dashboard.h(relative_review_file)}</code></p>
      {render_tagging_summary(tagging_record)}
    </section>
    {render_question_block(question, passage)}
    {render_retry_block(question, correct_choice)}
    {render_review_block(review, selected_choice, correct_choice)}
  </main>
  <script>{REVIEW_JS}</script>
</body>
</html>
"""


def render_tagging_summary(record: dict[str, Any] | None) -> str:
    if not record:
        return '<p class="note">No provisional tagging record is linked to this review file.</p>'
    tags = record.get("provisional_tags") or {}
    secondary = ", ".join(tags.get("secondary") or []) or "none"
    return f"""
    <dl class="review-summary">
      <div><dt>Primary tag</dt><dd><code>{dashboard.h(tags.get("primary"))}</code></dd></div>
      <div><dt>Secondary tags</dt><dd><code>{dashboard.h(secondary)}</code></dd></div>
      <div><dt>Confidence</dt><dd>{dashboard.h(tags.get("confidence"))}</dd></div>
    </dl>
    <p>{dashboard.h(record.get("tag_rationale"))}</p>
    """


def render_retry_block(question: dict[str, Any] | None, correct_choice: Any) -> str:
    if not question or not question.get("choices"):
        return """
        <section>
          <h2>Retry</h2>
          <p class="note">Canonical choices were not found, so this review cannot be retried here.</p>
        </section>
        """
    choices = "\n".join(
        f"""
        <label class="choice-option">
          <input type="radio" name="retry-choice" value="{dashboard.h(choice.get('choice_no'))}">
          <span>{dashboard.h(choice.get('choice_no'))}. {dashboard.h(choice.get('text'))}</span>
        </label>
        """
        for choice in question["choices"]
    )
    return f"""
    <section class="retry-panel" data-correct="{dashboard.h(correct_choice)}">
      <h2>Retry</h2>
      <p>Choose an answer, then check it locally. This does not modify the review file.</p>
      <fieldset>{choices}</fieldset>
      <button id="checkAnswer" type="button">Check Answer</button>
      <strong id="retryResult" aria-live="polite"></strong>
    </section>
    """


def render_question_block(question: dict[str, Any] | None, passage: dict[str, Any] | None) -> str:
    if not question:
        return """
        <section>
          <h2>Canonical Question</h2>
          <p class="note">Canonical question data was not found for this review.</p>
        </section>
        """
    passage_html = ""
    if passage:
        passage_html = f"""
        <details>
          <summary>Passage {dashboard.h(passage.get("id"))}</summary>
          <pre class="question-text">{dashboard.h(passage.get("body_text"))}</pre>
        </details>
        """
    return f"""
    <section>
      <h2>Canonical Question</h2>
      {passage_html}
      <pre class="question-text">{dashboard.h(question.get("stem"))}</pre>
    </section>
    """


def render_review_block(review: dict[str, Any], selected_choice: Any, correct_choice: Any) -> str:
    user_review = review.get("user_self_review") or {}
    feedback = review.get("assistant_feedback") or {}
    evidence = feedback.get("evidence") or []
    evidence_html = "".join(f"<li>{dashboard.h(item)}</li>" for item in evidence)
    return f"""
    <section>
      <h2>Original Review</h2>
      <dl class="review-summary">
        <div><dt>Selected</dt><dd>{dashboard.h(selected_choice)}</dd></div>
        <div><dt>Correct</dt><dd>{dashboard.h(correct_choice)}</dd></div>
        <div><dt>Status</dt><dd>{dashboard.h(review.get("status"))}</dd></div>
      </dl>
      <details>
        <summary>User self-review</summary>
        <p>{dashboard.h(user_review.get("reasoning_text"))}</p>
        <p>{dashboard.h(user_review.get("current_reflection"))}</p>
      </details>
      <details>
        <summary>Assistant feedback</summary>
        <p>{dashboard.h(feedback.get("diagnosis_text"))}</p>
        <ul>{evidence_html}</ul>
        <p><strong>Correction rule:</strong> {dashboard.h(feedback.get("correction_rule"))}</p>
      </details>
    </section>
    """


REVIEW_CSS = """
.review-main { max-width: 1100px; }
.review-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }
.review-summary div { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.review-summary dt { color: var(--muted); font-size: 12px; }
.review-summary dd { margin: 4px 0 0; font-weight: 700; }
.retry-panel fieldset { border: 0; padding: 0; margin: 0 0 12px; display: grid; gap: 8px; }
.choice-option { display: flex; gap: 8px; align-items: flex-start; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.choice-option input { margin-top: 3px; }
button { border: 1px solid var(--accent); background: var(--accent); color: white; border-radius: 6px; padding: 8px 12px; font-weight: 700; cursor: pointer; }
#retryResult { margin-left: 10px; }
.question-text { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; font-family: inherit; line-height: 1.55; }
"""


REVIEW_JS = """
const checkButton = document.getElementById('checkAnswer');
if (checkButton) {
  checkButton.addEventListener('click', () => {
    const panel = document.querySelector('.retry-panel');
    const selected = document.querySelector('input[name="retry-choice"]:checked');
    const result = document.getElementById('retryResult');
    if (!selected) {
      result.textContent = 'Choose an answer first.';
      result.style.color = 'var(--warn)';
      return;
    }
    const correct = panel.dataset.correct;
    const isCorrect = selected.value === correct;
    result.textContent = isCorrect ? 'Correct.' : `Incorrect. Correct answer: ${correct}`;
    result.style.color = isCorrect ? 'var(--accent)' : 'var(--danger)';
  });
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the LEET tagging dashboard from live repo data.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), TaggingDashboardHandler)
    url = f"http://{args.host}:{server.server_port}/"
    print(f"Serving live tagging dashboard at {url}")
    print("API endpoint: /api/dashboard")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
