"""Human verification workflow for OCR crop suggestions."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator

from leet_practice.models import Choice, TextStatus

_review_state_lock = threading.RLock()


class VerificationError(RuntimeError):
    """Raised when verification data is invalid."""


class ReviewStatus(StrEnum):
    """Review status for a crop suggestion."""

    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    NEEDS_FIX = "needs_fix"
    REJECTED = "rejected"


class CandidateType(StrEnum):
    """Normalized candidate type."""

    PASSAGE = "passage"
    QUESTION = "question"


class ReviewCandidate(BaseModel):
    """One candidate item in the human review queue."""

    candidate_id: str
    suggestion_id: str
    candidate_type: CandidateType
    status: ReviewStatus = ReviewStatus.UNREVIEWED
    question_number: int | None = Field(default=None, gt=0)
    start_question: int | None = Field(default=None, gt=0)
    end_question: int | None = Field(default=None, gt=0)
    preview_path: str | None = None
    raw_ocr_text: str = ""
    verified_text: str = ""
    stem: str = ""
    choices: list[str] = Field(default_factory=lambda: ["", "", "", "", ""])
    correct_answer: int | None = Field(default=None, ge=1, le=5)
    passage_id: str | None = None
    notes: str = ""
    ocr_draft_text: str = ""
    prefill_source: str | None = None
    prefill_warnings: list[str] = Field(default_factory=list)
    correction_steps: list[str] = Field(default_factory=list)
    manually_edited: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("choices")
    @classmethod
    def normalize_choices(cls, value: list[str]) -> list[str]:
        normalized = [str(item) for item in value]
        if len(normalized) < 5:
            normalized.extend([""] * (5 - len(normalized)))
        return normalized[:5]


class ReviewState(BaseModel):
    """Persistent state for a crop-review session."""

    exam_id: str
    suggestions_path: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    draft_options: dict[str, Any] = Field(default_factory=dict)
    candidates: list[ReviewCandidate] = Field(default_factory=list)


class DraftOptions(BaseModel):
    """Optional OCR draft enhancement switches."""

    enable_spacing_cleanup: bool = False
    enable_morphology_checks: bool = False
    local_nlp_workers: int = Field(default_factory=lambda: min(os.cpu_count() or 1, 4), ge=1)


class OcrDraft(BaseModel):
    """Structured draft generated from raw OCR text."""

    draft_text: str
    verified_text: str = ""
    stem: str = ""
    choices: list[str] = Field(default_factory=lambda: ["", "", "", "", ""])
    warnings: list[str] = Field(default_factory=list)
    correction_steps: list[str] = Field(default_factory=list)

    @field_validator("choices")
    @classmethod
    def normalize_choices(cls, value: list[str]) -> list[str]:
        normalized = [str(item) for item in value]
        if len(normalized) < 5:
            normalized.extend([""] * (5 - len(normalized)))
        return normalized[:5]


@dataclass(frozen=True)
class SpacingBackend:
    name: str
    apply: Callable[[str], str]


@dataclass
class CleanupBackends:
    """Cached optional local NLP backends for one review-state initialization."""

    spacing_backend: SpacingBackend | None = None
    spacing_setup_warning: str | None = None
    kiwi: Any | None = None
    kiwi_setup_warning: str | None = None
    local_nlp_workers: int = 1


class VerifiedPassageDraft(BaseModel):
    """Accepted passage draft staged before canonical promotion."""

    id: str
    exam_id: str
    passage_no: int = Field(gt=0)
    question_range: tuple[int, int]
    body_text: str
    text_status: TextStatus = TextStatus.VERIFIED
    source_provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question_range")
    @classmethod
    def validate_question_range(cls, value: tuple[int, int]) -> tuple[int, int]:
        start, end = value
        if start <= 0 or end < start:
            raise ValueError("question_range must be positive and ordered")
        return value


class VerifiedQuestionDraft(BaseModel):
    """Accepted question draft staged before canonical promotion."""

    id: str
    exam_id: str
    question_no: int = Field(gt=0)
    passage_id: str | None = None
    stem: str
    choices: list[Choice]
    correct_answer: int = Field(ge=1, le=5)
    text_status: TextStatus = TextStatus.VERIFIED
    source_provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("choices")
    @classmethod
    def require_five_choices(cls, value: list[Choice]) -> list[Choice]:
        if len(value) != 5:
            raise ValueError("questions must have exactly five choices")
        return value


def verification_dir(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return data_root / "verification" / exam_id


def canonical_dir(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return data_root / "canonical" / exam_id


def review_state_path(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return verification_dir(exam_id, data_root=data_root) / "crop-review-state.json"


def passage_drafts_path(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return verification_dir(exam_id, data_root=data_root) / "verified_passages.jsonl"


def question_drafts_path(exam_id: str, *, data_root: Path = Path("data")) -> Path:
    return verification_dir(exam_id, data_root=data_root) / "verified_questions.jsonl"


def _now() -> datetime:
    return datetime.now()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(row.model_dump_json() for row in rows)
    path.write_text((text + "\n") if text else "", encoding="utf-8")


def _write_jsonl_atomic(path: Path, rows: list[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    backup_path = path.with_name(f"{path.name}.bak")
    text = "\n".join(row.model_dump_json() for row in rows)
    temp_path.write_text((text + "\n") if text else "", encoding="utf-8")
    if path.exists():
        shutil.copy2(path, backup_path)
    os.replace(temp_path, path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug.strip("_") or "candidate"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _resolve_artifact_path(raw_path: str | None, suggestions_dir: Path) -> str | None:
    if not raw_path:
        return None
    suggestions_root = suggestions_dir.resolve()
    path = Path(raw_path)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        repo_relative = path.resolve()
        suggestion_relative = (suggestions_root / path).resolve()
        if _is_relative_to(repo_relative, suggestions_root) and (repo_relative.exists() or not suggestion_relative.exists()):
            resolved = repo_relative
        else:
            resolved = suggestion_relative
    if not _is_relative_to(resolved, suggestions_root):
        raise VerificationError(f"Artifact path escapes suggestions directory: {raw_path}")
    return str(resolved)


def _candidate_type(kind: str) -> CandidateType | None:
    if "passage" in kind:
        return CandidateType.PASSAGE
    if "question" in kind:
        return CandidateType.QUESTION
    return None


CHOICE_MARKER_RE = re.compile(
    r"^\s*(?P<marker>[\u2460-\u2464]|[1-5][.)\uff0e\uff09]|[(\uff08][1-5][)\uff09]|[1-5])\s*(?P<text>.*)$"
)
VIEW_HEADING_RE = re.compile(r"^<\s*\ubcf4\s*\uae30\s*>$")
VIEW_ITEM_MARKER_RE = re.compile(r"^(?:[\u3131-\u314e]|7)\s*[.)]\s*")
PASSAGE_SECTION_LABEL_RE = re.compile(r"^\([^\s()]{1,3}\)$")
PASSAGE_BRACKETED_DIRECTION_RE = re.compile(r"^\[[^\]]+\]$")
PASSAGE_SPEAKER_RE = re.compile(r"^[\uac00-\ud7a3A-Za-z][\uac00-\ud7a3A-Za-z\s]{0,8}:")
PASSAGE_STANDALONE_DIRECTION_RE = re.compile(r"^\([^)]*\)$")
PASSAGE_SOURCE_RE = re.compile(r"^[-\u2014].+[-\u2014]$")
PASSAGE_FOOTNOTE_RE = re.compile(r"^\*")
PASSAGE_HEADER_RE = re.compile(
    r"(?P<header>(?:\[\s*\d+\s*[~～-]\s*\d+\s*\]\s*)?다음\s+글을\s+읽고\s+물음에\s+답하시오\.)\s*"
)
PASSAGE_HEADER_STEP = "formatted_passage_header_break"
CHOICE_MARKER_TO_INDEX = {
    "\u2460": 1,
    "\u2461": 2,
    "\u2462": 3,
    "\u2463": 4,
    "\u2464": 5,
    "1)": 1,
    "2)": 2,
    "3)": 3,
    "4)": 4,
    "5)": 5,
    "1.": 1,
    "2.": 2,
    "3.": 3,
    "4.": 4,
    "5.": 5,
    "1\uff0e": 1,
    "2\uff0e": 2,
    "3\uff0e": 3,
    "4\uff0e": 4,
    "5\uff0e": 5,
    "1\uff09": 1,
    "2\uff09": 2,
    "3\uff09": 3,
    "4\uff09": 4,
    "5\uff09": 5,
    "(1)": 1,
    "(2)": 2,
    "(3)": 3,
    "(4)": 4,
    "(5)": 5,
    "\uff081\uff09": 1,
    "\uff082\uff09": 2,
    "\uff083\uff09": 3,
    "\uff084\uff09": 4,
    "\uff085\uff09": 5,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
}


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]


KOREAN_CONTINUATION_EXACT = {
    "\uac00",
    "\uace0",
    "\ub098",
    "\ub294",
    "\ub3c4",
    "\ub97c",
    "\ub8f0",
    "\ub85c",
    "\ub9cc",
    "\uba70",
    "\ub294",
    "\uc640",
    "\uc73c\ub85c",
    "\uc740",
    "\uc744",
    "\uc758",
    "\uc774",
}
KOREAN_CONTINUATION_PREFIXES = (
    "\ud558",
    "\ud55c",
    "\ub418",
    "\ub41c",
    "\ub420",
    "\ub418\ub294",
    "\ub418\uc9c0",
    "\uc5d0\uac8c",
    "\uc5d0\uc11c",
    "\ubd80\ud130",
    "\uae4c\uc9c0",
    "\ucc98\ub7fc",
    "\ubcf4\ub2e4",
    "\uc870\ucc28",
    "\ub9c8\uc800",
    "\ub77c\ub3c4",
    "\uc774\ub77c",
    "\uc774\ub098",
)
HEADER_FOOTER_EDGE_TEXT_RE = re.compile(
    r"^(?:"
    r"\uc5b8\uc5b4|\uc774\ud574|\uc5b8\d+|"
    r"\ucd94\ub9ac|\ub17c\uc99d|\ub17c\uc220|"
    r"\ud640\uc218\ud615|\uc9dd\uc218\ud615|"
    r"\uc131\uba85|\uc218\ud5d8|\ubc88\ud638|\uc218\ud5d8\ubc88\ud638|\uad50\uc2dc|"
    r"\d+\s*\ud638|\uadf8\ud638"
    r")$"
)
HEADER_FOOTER_TOP_EDGE_RATIO = 0.18
HEADER_FOOTER_BOTTOM_EDGE_RATIO = 0.92


def _is_korean_continuation(prev_line: str, next_line: str) -> bool:
    prev = prev_line.rstrip()
    next_text = next_line.lstrip()
    if not prev or not next_text or not re.search(r"[\uac00-\ud7a3]$", prev):
        return False
    if re.search(r"[.!?\u3002\uff01\uff1f\"')\]\}]\s*$", prev):
        return False
    first_token = next_text.split(maxsplit=1)[0]
    return first_token in KOREAN_CONTINUATION_EXACT or first_token.startswith(KOREAN_CONTINUATION_PREFIXES)


def _join_wrapped_pair(left: str, right: str) -> str:
    left = left.strip()
    right = right.strip()
    if not left:
        return right
    if not right:
        return left
    separator = "" if _is_korean_continuation(left, right) else " "
    return f"{left}{separator}{right}"


def _join_wrapped_lines(lines: list[str]) -> str:
    joined = ""
    for line in lines:
        if not line.strip():
            continue
        joined = _join_wrapped_pair(joined, line) if joined else line.strip()
    return joined


def _join_wrapped_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n+", normalized)
    joined = [_join_passage_paragraph(paragraph.split("\n")) for paragraph in paragraphs]
    return "\n\n".join(paragraph for paragraph in joined if paragraph)


def _is_passage_block_start(line: str) -> bool:
    return bool(
        PASSAGE_SECTION_LABEL_RE.fullmatch(line)
        or PASSAGE_BRACKETED_DIRECTION_RE.fullmatch(line)
        or PASSAGE_SPEAKER_RE.match(line)
        or PASSAGE_STANDALONE_DIRECTION_RE.fullmatch(line)
        or PASSAGE_SOURCE_RE.match(line)
        or PASSAGE_FOOTNOTE_RE.match(line)
    )


def _join_passage_paragraph(lines: list[str]) -> str:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if current and _is_passage_block_start(stripped):
            blocks.append(current)
            current = []
        current.append(stripped)
    if current:
        blocks.append(current)
    return "\n".join(_join_wrapped_lines(block) for block in blocks if block)


def _format_passage_header_break(text: str) -> str:
    match = PASSAGE_HEADER_RE.search(text)
    if match is None or match.start() > 80:
        return text
    body = text[match.end() :]
    if not body.strip():
        return text
    return text[: match.start()] + match.group("header").strip() + "\n\n" + body.lstrip()


def _join_question_stem_lines(lines: list[str]) -> str:
    blocks: list[list[str]] = []
    current: list[str] = []
    in_view_block = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if VIEW_HEADING_RE.fullmatch(stripped):
            if current:
                blocks.append(current)
            blocks.append([stripped])
            current = []
            in_view_block = True
            continue
        if in_view_block and VIEW_ITEM_MARKER_RE.match(stripped):
            if current:
                blocks.append(current)
            current = [stripped]
            continue
        current.append(stripped)
    if current:
        blocks.append(current)
    return "\n".join(_join_wrapped_lines(block) for block in blocks if block)


def _normalize_punctuation_spacing(text: str) -> str:
    text = re.sub(r"(?<=[^\s\d])([,;:])(?=[^\s\d])", r"\1 ", text)
    return re.sub(r"(?<=[\w\uac00-\ud7a3\u3131-\u318e])([.!?])(?=[A-Za-z\uac00-\ud7a3\u3131-\u318e])", r"\1 ", text)


def _remove_leading_question_marker(line: str, question_number: int | None) -> tuple[str, bool]:
    if question_number is None:
        return line, False
    pattern = re.compile(rf"^\s*(?:\ubb38\s*)?{question_number}(?:\s*[.)\uff0e\uff09]\s*|\s+)")
    stripped = pattern.sub("", line, count=1).strip()
    return stripped, stripped != line.strip()


def _choice_index(marker: str) -> int | None:
    return CHOICE_MARKER_TO_INDEX.get(marker)


def _is_circled_choice_marker(marker: str) -> bool:
    return "\u2460" <= marker <= "\u2464"


def _build_kiwi(workers: int | None = None) -> tuple[Any | None, str | None]:
    try:
        module = import_module("kiwipiepy")
    except ImportError:
        return None, "kiwi_backend_unavailable"
    if not hasattr(module, "Kiwi"):
        return None, "kiwi_backend_unavailable:no_kiwi_class"
    try:
        if workers is None:
            return module.Kiwi(), None
        return module.Kiwi(num_workers=workers), None
    except TypeError:
        try:
            return module.Kiwi(), None
        except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
            return None, f"kiwi_backend_failed:{exc}"
    except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
        return None, f"kiwi_backend_failed:{exc}"


def build_cleanup_backends(options: DraftOptions | None = None) -> CleanupBackends:
    """Resolve optional local NLP backends once for a batch of OCR drafts."""

    options = options or DraftOptions()
    backends = CleanupBackends(local_nlp_workers=options.local_nlp_workers)

    if options.enable_spacing_cleanup:
        try:
            module = import_module("pykospacing")
        except ImportError:
            module = None
        if module is not None and hasattr(module, "Spacing"):
            try:
                spacing = module.Spacing()
            except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
                backends.spacing_setup_warning = f"spacing_backend_failed:pykospacing:{exc}"
                return backends
            backends.spacing_backend = SpacingBackend("pykospacing", spacing)
            if options.enable_morphology_checks:
                backends.kiwi, backends.kiwi_setup_warning = _build_kiwi(options.local_nlp_workers)
            return backends

        try:
            module = import_module("korspacing")
        except ImportError:
            module = None
        if module is not None:
            try:
                if hasattr(module, "Spacing"):
                    spacing = module.Spacing()
                    backends.spacing_backend = SpacingBackend("korspacing", spacing)
                elif hasattr(module, "space"):
                    backends.spacing_backend = SpacingBackend("korspacing", module.space)
                else:
                    backends.spacing_setup_warning = "spacing_backend_unavailable:no_supported_api"
                if options.enable_morphology_checks:
                    backends.kiwi, backends.kiwi_setup_warning = _build_kiwi(options.local_nlp_workers)
                return backends
            except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
                backends.spacing_setup_warning = f"spacing_backend_failed:korspacing:{exc}"
                return backends

        spacing_kiwi, spacing_kiwi_warning = _build_kiwi()
        if spacing_kiwi is None:
            if spacing_kiwi_warning == "kiwi_backend_unavailable:no_kiwi_class":
                backends.spacing_setup_warning = "spacing_backend_unavailable:kiwipiepy:no_kiwi_class"
            elif spacing_kiwi_warning and spacing_kiwi_warning.startswith("kiwi_backend_failed:"):
                backends.spacing_setup_warning = spacing_kiwi_warning.replace(
                    "kiwi_backend_failed:",
                    "spacing_backend_failed:kiwipiepy:",
                    1,
                )
            else:
                backends.spacing_setup_warning = "spacing_backend_unavailable"
        else:
            backends.spacing_backend = SpacingBackend("kiwipiepy", spacing_kiwi.space)

    if options.enable_morphology_checks and backends.kiwi is None:
        backends.kiwi, backends.kiwi_setup_warning = _build_kiwi(options.local_nlp_workers)

    return backends


def _apply_spacing_cleanup(text: str, backends: CleanupBackends | None = None) -> tuple[str, list[str], list[str]]:
    warnings: list[str] = []
    steps: list[str] = []
    if backends is not None:
        if backends.spacing_setup_warning:
            return text, [backends.spacing_setup_warning], []
        if backends.spacing_backend is None:
            return text, ["spacing_backend_unavailable"], steps
        try:
            corrected = backends.spacing_backend.apply(text)
        except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
            return text, [f"spacing_backend_failed:{backends.spacing_backend.name}:{exc}"], []
        return str(corrected), warnings, [f"spacing_cleanup:{backends.spacing_backend.name}"]

    try:
        module = import_module("pykospacing")
    except ImportError:
        module = None
    if module is not None and hasattr(module, "Spacing"):
        try:
            corrected = module.Spacing()(text)
        except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
            return text, [f"spacing_backend_failed:pykospacing:{exc}"], []
        return str(corrected), warnings, ["spacing_cleanup:pykospacing"]

    try:
        module = import_module("korspacing")
    except ImportError:
        module = None
    if module is not None:
        try:
            if hasattr(module, "Spacing"):
                corrected = module.Spacing()(text)
            elif hasattr(module, "space"):
                corrected = module.space(text)
            else:
                return text, ["spacing_backend_unavailable:no_supported_api"], []
        except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
            return text, [f"spacing_backend_failed:korspacing:{exc}"], []
        return str(corrected), warnings, ["spacing_cleanup:korspacing"]

    try:
        module = import_module("kiwipiepy")
    except ImportError:
        module = None
    if module is not None:
        if not hasattr(module, "Kiwi"):
            return text, ["spacing_backend_unavailable:kiwipiepy:no_kiwi_class"], []
        try:
            corrected = module.Kiwi().space(text)
        except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
            return text, [f"spacing_backend_failed:kiwipiepy:{exc}"], []
        return str(corrected), warnings, ["spacing_cleanup:kiwipiepy"]

    return text, ["spacing_backend_unavailable"], steps


def _kiwi_morphology_warnings(text: str, backends: CleanupBackends | None = None) -> tuple[list[str], list[str]]:
    if backends is not None:
        if backends.kiwi is None:
            return [backends.kiwi_setup_warning or "kiwi_backend_unavailable"], []
        try:
            tokens = backends.kiwi.tokenize(text)
        except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
            return [f"kiwi_backend_failed:{exc}"], []
        return _morphology_warnings_from_tokens(text, tokens)

    try:
        module = import_module("kiwipiepy")
    except ImportError:
        return ["kiwi_backend_unavailable"], []
    if not hasattr(module, "Kiwi"):
        return ["kiwi_backend_unavailable:no_kiwi_class"], []
    try:
        tokens = module.Kiwi().tokenize(text)
    except Exception as exc:  # noqa: BLE001 - optional backend should not break review.
        return [f"kiwi_backend_failed:{exc}"], []

    return _morphology_warnings_from_tokens(text, tokens)


def _morphology_warnings_from_tokens(text: str, tokens: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    hangul_chars = len(re.findall(r"[\uac00-\ud7a3]", text))
    token_count = len(tokens or [])
    if hangul_chars and token_count == 0:
        warnings.append("kiwi_no_tokens_for_hangul")
    if hangul_chars >= 10 and token_count / max(hangul_chars, 1) > 0.85:
        warnings.append("kiwi_fragmented_tokenization")
    if re.search(r"[\ufffd\u25a1]{1,}|\?{2,}", text):
        warnings.append("suspicious_ocr_fragments")
    return warnings, ["kiwi_morphology_checked"]


def _kiwi_morphology_warnings_batch(
    texts: list[str],
    backends: CleanupBackends,
) -> list[tuple[list[str], list[str]]]:
    if backends.kiwi is None:
        return [([backends.kiwi_setup_warning or "kiwi_backend_unavailable"], []) for _ in texts]
    try:
        analyze = getattr(backends.kiwi, "analyze")
        analyzed = list(analyze(texts))
        if len(analyzed) != len(texts):
            raise ValueError("Kiwi batch analysis returned an unexpected result count")
        results: list[tuple[list[str], list[str]]] = []
        for text, item in zip(texts, analyzed, strict=True):
            tokens = item[0] if isinstance(item, tuple) and item else item
            results.append(_morphology_warnings_from_tokens(text, tokens))
        return results
    except Exception:
        return [_kiwi_morphology_warnings(text, backends) for text in texts]


def generate_ocr_draft(
    candidate_type: CandidateType,
    raw_ocr_text: str,
    *,
    question_number: int | None = None,
    options: DraftOptions | None = None,
    cleanup_backends: CleanupBackends | None = None,
    morphology_result: tuple[list[str], list[str]] | None = None,
) -> OcrDraft:
    """Generate a review draft from raw OCR text without changing the raw text."""

    options = options or DraftOptions()
    text = raw_ocr_text.strip()
    warnings: list[str] = []
    steps: list[str] = ["ocr_heuristic_prefill"]

    if options.enable_spacing_cleanup and text:
        text, spacing_warnings, spacing_steps = _apply_spacing_cleanup(text, cleanup_backends)
        warnings.extend(spacing_warnings)
        steps.extend(spacing_steps)

    if options.enable_morphology_checks and text:
        kiwi_warnings, kiwi_steps = morphology_result or _kiwi_morphology_warnings(text, cleanup_backends)
        warnings.extend(kiwi_warnings)
        steps.extend(kiwi_steps)

    normalized_text = _normalize_punctuation_spacing(text)
    if normalized_text != text:
        text = normalized_text
        steps.append("normalized_punctuation_spacing")

    joined_text = _join_wrapped_text(text)
    if joined_text != text:
        steps.append("joined_forced_line_breaks")

    if candidate_type == CandidateType.PASSAGE:
        formatted_text = _format_passage_header_break(joined_text)
        if formatted_text != joined_text:
            joined_text = formatted_text
            steps.append(PASSAGE_HEADER_STEP)
        return OcrDraft(
            draft_text=text,
            verified_text=joined_text,
            warnings=warnings,
            correction_steps=steps,
        )

    lines = _clean_lines(text)
    if lines:
        lines[0], removed = _remove_leading_question_marker(lines[0], question_number)
        if removed:
            steps.append("removed_leading_question_marker")
    stem_lines: list[str] = []
    choice_lines: dict[int, list[str]] = {}
    current_choice: int | None = None
    duplicate_choices: set[int] = set()
    ignored_markers: list[int] = []
    for line in lines:
        match = CHOICE_MARKER_RE.match(line)
        if match:
            index = _choice_index(match.group("marker"))
            if index is None:
                stem_lines.append(line)
                current_choice = None
                continue
            expected_index = 1 if not choice_lines else max(choice_lines) + 1
            if index != expected_index and not (index in choice_lines and _is_circled_choice_marker(match.group("marker"))):
                if choice_lines and index > expected_index:
                    ignored_markers.extend(range(expected_index, index))
                else:
                    ignored_markers.append(index)
                    if current_choice is not None:
                        choice_lines[current_choice].append(line)
                    else:
                        stem_lines.append(line)
                    continue
            if index in choice_lines:
                duplicate_choices.add(index)
            choice_lines.setdefault(index, [])
            choice_text = match.group("text").strip()
            if choice_text:
                choice_lines[index].append(choice_text)
            current_choice = index
            continue
        if current_choice is not None:
            choice_lines[current_choice].append(line)
        else:
            stem_lines.append(line)

    detected = sorted(choice_lines)
    if not detected:
        warnings.append("no_choices_detected")
    elif detected != [1, 2, 3, 4, 5]:
        warnings.append(f"choices_detected_{len(detected)}")
    if duplicate_choices:
        warnings.append("duplicate_choice_markers:" + ",".join(str(index) for index in sorted(duplicate_choices)))
    if ignored_markers:
        warnings.append("ignored_out_of_sequence_choice_markers:" + ",".join(str(index) for index in sorted(set(ignored_markers))))

    choices = ["", "", "", "", ""]
    for index, parts in choice_lines.items():
        if 1 <= index <= 5:
            choices[index - 1] = _join_wrapped_lines(parts)

    return OcrDraft(
        draft_text=text,
        stem=_join_question_stem_lines(stem_lines),
        choices=choices,
        warnings=warnings,
        correction_steps=steps,
    )


def apply_ocr_draft(
    candidate: ReviewCandidate,
    options: DraftOptions | None = None,
    *,
    cleanup_backends: CleanupBackends | None = None,
    morphology_result: tuple[list[str], list[str]] | None = None,
) -> ReviewCandidate:
    draft = generate_ocr_draft(
        candidate.candidate_type,
        candidate.raw_ocr_text,
        question_number=candidate.question_number,
        options=options,
        cleanup_backends=cleanup_backends,
        morphology_result=morphology_result,
    )
    patch = candidate.model_dump()
    patch["ocr_draft_text"] = draft.draft_text
    patch["prefill_source"] = "ocr_heuristic"
    patch["prefill_warnings"] = draft.warnings
    patch["correction_steps"] = draft.correction_steps
    if candidate.candidate_type == CandidateType.PASSAGE:
        patch["verified_text"] = draft.verified_text
    else:
        patch["stem"] = draft.stem
        patch["choices"] = draft.choices
    return ReviewCandidate.model_validate(patch)


def _texts_after_spacing_cleanup(
    candidates: list[ReviewCandidate],
    options: DraftOptions,
    cleanup_backends: CleanupBackends | None,
) -> list[str]:
    texts: list[str] = []
    for candidate in candidates:
        text = candidate.raw_ocr_text.strip()
        if options.enable_spacing_cleanup and text:
            text, _, _ = _apply_spacing_cleanup(text, cleanup_backends)
        texts.append(text)
    return texts


def apply_ocr_drafts(
    candidates: list[ReviewCandidate],
    options: DraftOptions | None = None,
    *,
    cleanup_backends: CleanupBackends | None = None,
) -> list[ReviewCandidate]:
    options = options or DraftOptions()
    cleanup_backends = cleanup_backends or build_cleanup_backends(options)
    morphology_results: list[tuple[list[str], list[str]] | None] = [None] * len(candidates)
    if options.enable_morphology_checks and not options.enable_spacing_cleanup:
        morphology_texts = _texts_after_spacing_cleanup(candidates, options, cleanup_backends)
        non_empty_indexes = [index for index, text in enumerate(morphology_texts) if text]
        non_empty_texts = [morphology_texts[index] for index in non_empty_indexes]
        batch_results = _kiwi_morphology_warnings_batch(non_empty_texts, cleanup_backends) if non_empty_texts else []
        for index, result in zip(non_empty_indexes, batch_results, strict=True):
            morphology_results[index] = result
    return [
        apply_ocr_draft(
            candidate,
            options,
            cleanup_backends=cleanup_backends,
            morphology_result=morphology_results[index],
        )
        for index, candidate in enumerate(candidates)
    ]


def _row_indices(row_ids: list[Any]) -> set[int]:
    indices: set[int] = set()
    for row_id in row_ids:
        match = re.search(r"_r(\d+)$", str(row_id))
        if match:
            indices.add(int(match.group(1)))
    return indices


def _ocr_json_path_for_part(part: dict[str, Any], suggestions_dir: Path) -> Path:
    page = int(part["page"])
    column = str(part["column"])
    return suggestions_dir / f"page_{page:03d}_{column}.paddleocr.json"


def _row_center_in_bbox(row: dict[str, Any], bbox: list[Any] | None) -> bool:
    if not bbox or len(bbox) != 4:
        return False
    row_bbox = row.get("local_bbox")
    if not isinstance(row_bbox, list) or len(row_bbox) != 4:
        return False
    try:
        crop_left, crop_top, crop_right, crop_bottom = [float(value) for value in bbox]
        row_left, row_top, row_right, row_bottom = [float(value) for value in row_bbox]
    except (TypeError, ValueError):
        return False
    center_x = (row_left + row_right) / 2
    center_y = (row_top + row_bottom) / 2
    return crop_left <= center_x <= crop_right and crop_top <= center_y <= crop_bottom


def _row_left(row: dict[str, Any]) -> float | None:
    row_bbox = row.get("local_bbox")
    if not isinstance(row_bbox, list) or len(row_bbox) != 4:
        return None
    try:
        return float(row_bbox[0])
    except (TypeError, ValueError):
        return None


def _is_header_footer_artifact(row: dict[str, Any], payload: dict[str, Any]) -> bool:
    text = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()
    if not text:
        return False
    row_bbox = row.get("local_bbox")
    local_size = payload.get("local_size")
    if not isinstance(row_bbox, list) or len(row_bbox) != 4:
        return False
    if not isinstance(local_size, list) or len(local_size) != 2:
        return False
    try:
        height = float(local_size[1])
        row_top = float(row_bbox[1])
        row_bottom = float(row_bbox[3])
    except (TypeError, ValueError):
        return False
    near_top = row_top <= height * HEADER_FOOTER_TOP_EDGE_RATIO
    near_bottom = row_bottom >= height * HEADER_FOOTER_BOTTOM_EDGE_RATIO
    return (near_top or near_bottom) and bool(HEADER_FOOTER_EDGE_TEXT_RE.fullmatch(text))


def _body_left_for_rows(rows: list[dict[str, Any]]) -> float | None:
    lefts = sorted(left for row in rows if (left := _row_left(row)) is not None)
    if not lefts:
        return None
    return lefts[len(lefts) // 2]


def _is_indented_paragraph_start(row: dict[str, Any], body_left: float | None) -> bool:
    left = _row_left(row)
    if left is None or body_left is None:
        return False
    return left - body_left >= 30


def collect_raw_ocr_text(candidate: dict[str, Any], suggestions_dir: Path) -> str:
    """Collect compact OCR text for the rows included in candidate crop parts."""

    lines: list[str] = []
    seen: set[tuple[Path, int]] = set()
    is_passage = _candidate_type(str(candidate.get("kind") or "")) == CandidateType.PASSAGE
    for part in candidate.get("parts") or []:
        if not isinstance(part, dict):
            continue
        try:
            ocr_path = _ocr_json_path_for_part(part, suggestions_dir)
        except (KeyError, TypeError, ValueError):
            continue
        if not ocr_path.exists():
            continue
        crop_bbox = part.get("local_crop_bbox")
        row_indices = _row_indices(list(part.get("included_row_ids") or []))
        if not row_indices and not crop_bbox:
            continue
        payload = _read_json(ocr_path)
        rows = payload.get("rows") or []
        part_rows: list[dict[str, Any]] = []
        for row in rows:
            row_index = row.get("row_index")
            if (row_index not in row_indices and not _row_center_in_bbox(row, crop_bbox)) or (ocr_path, row_index) in seen:
                continue
            if _is_header_footer_artifact(row, payload):
                continue
            seen.add((ocr_path, row_index))
            part_rows.append(row)
        body_left = _body_left_for_rows(part_rows) if is_passage else None
        for row in part_rows:
            text = str(row.get("text") or "").strip()
            if text and is_passage and lines and lines[-1] != "" and _is_indented_paragraph_start(row, body_left):
                lines.append("")
            lines.append(text)
    return "\n".join(lines)


def passage_id_for(exam_id: str, start_question: int, end_question: int) -> str:
    return f"{exam_id}-passage-{start_question:03d}-{end_question:03d}"


def question_id_for(exam_id: str, question_no: int) -> str:
    return f"{exam_id}-q{question_no:03d}"


def parse_suggestions(
    exam_id: str,
    suggestions_path: Path,
    *,
    draft_options: DraftOptions | None = None,
) -> ReviewState:
    """Parse a crop-suggestion artifact into a review state."""

    draft_options = draft_options or DraftOptions()
    suggestions_path = suggestions_path.resolve()
    payload = _read_json(suggestions_path)
    suggestions_dir = suggestions_path.parent
    candidates: list[ReviewCandidate] = []
    candidate_ids: set[str] = set()
    for index, item in enumerate(payload.get("suggestions") or [], start=1):
        if not isinstance(item, dict):
            continue
        normalized_type = _candidate_type(str(item.get("kind") or ""))
        if normalized_type is None:
            continue
        suggestion_id = str(item.get("suggestion_id") or f"candidate_{index:03d}")
        start_question = item.get("start_question") or item.get("set_start_question")
        end_question = item.get("end_question") or item.get("set_end_question")
        passage_id = None
        if normalized_type == CandidateType.QUESTION and start_question and end_question:
            passage_id = passage_id_for(exam_id, int(start_question), int(end_question))
        candidate_id = _slug(suggestion_id)
        if candidate_id in candidate_ids:
            raise VerificationError(f"Duplicate candidate_id after slug normalization: {candidate_id}")
        candidate_ids.add(candidate_id)
        candidate = ReviewCandidate(
            candidate_id=candidate_id,
            suggestion_id=suggestion_id,
            candidate_type=normalized_type,
            question_number=item.get("question_number"),
            start_question=start_question,
            end_question=end_question,
            preview_path=_resolve_artifact_path(item.get("candidate_preview_path"), suggestions_dir),
            raw_ocr_text=collect_raw_ocr_text(item, suggestions_dir),
            passage_id=passage_id,
            provenance={
                "suggestions_path": str(suggestions_path),
                "original": item,
            },
        )
        candidates.append(candidate)
    return ReviewState(
        exam_id=exam_id,
        suggestions_path=str(suggestions_path),
        draft_options=draft_options.model_dump(),
        candidates=apply_ocr_drafts(
            candidates,
            draft_options,
            cleanup_backends=build_cleanup_backends(draft_options),
        ),
    )


def load_review_state(exam_id: str, *, data_root: Path = Path("data")) -> ReviewState:
    path = review_state_path(exam_id, data_root=data_root)
    if not path.exists():
        raise VerificationError(f"Review state does not exist: {path}")
    return ReviewState.model_validate(_read_json(path))


def save_review_state(state: ReviewState, *, data_root: Path = Path("data")) -> Path:
    state.updated_at = _now()
    path = review_state_path(state.exam_id, data_root=data_root)
    _write_json(path, state.model_dump(mode="json"))
    return path


def _has_review_edits(candidate: ReviewCandidate) -> bool:
    return bool(
        candidate.manually_edited
        or candidate.status != ReviewStatus.UNREVIEWED
        or candidate.notes.strip()
        or candidate.correct_answer is not None
    )


_REVIEW_DECISION_FIELDS = ("status", "correct_answer", "notes")
_OCR_DRAFT_EDITABLE_FIELDS = ("verified_text", "stem", "choices")


def _preserve_review_edits(fresh: ReviewState, existing: ReviewState) -> ReviewState:
    existing_by_id = {candidate.candidate_id: candidate for candidate in existing.candidates}
    merged_candidates: list[ReviewCandidate] = []
    for fresh_candidate in fresh.candidates:
        existing_candidate = existing_by_id.get(fresh_candidate.candidate_id)
        if existing_candidate is None or not _has_review_edits(existing_candidate):
            merged_candidates.append(fresh_candidate)
            continue
        patch = fresh_candidate.model_dump()
        for key in _REVIEW_DECISION_FIELDS:
            patch[key] = getattr(existing_candidate, key)
        if existing_candidate.manually_edited:
            for key in _OCR_DRAFT_EDITABLE_FIELDS:
                patch[key] = getattr(existing_candidate, key)
            patch["manually_edited"] = True
        merged_candidates.append(ReviewCandidate.model_validate(patch))
    fresh.candidates = merged_candidates
    return fresh


def initialize_review_state(
    exam_id: str,
    suggestions_path: Path,
    *,
    data_root: Path = Path("data"),
    overwrite: bool = False,
    refresh_preserving_edits: bool = False,
    enable_spacing_cleanup: bool = False,
    enable_morphology_checks: bool = False,
    local_nlp_workers: int | None = None,
) -> ReviewState:
    """Create or load review state for a suggestions file."""

    path = review_state_path(exam_id, data_root=data_root)
    if path.exists() and not overwrite and not refresh_preserving_edits:
        return load_review_state(exam_id, data_root=data_root)
    existing = load_review_state(exam_id, data_root=data_root) if path.exists() and refresh_preserving_edits else None
    draft_options = DraftOptions(
        enable_spacing_cleanup=enable_spacing_cleanup,
        enable_morphology_checks=enable_morphology_checks,
        local_nlp_workers=local_nlp_workers or min(os.cpu_count() or 1, 4),
    )
    state = parse_suggestions(exam_id, suggestions_path, draft_options=draft_options)
    if existing is not None:
        state = _preserve_review_edits(state, existing)
    save_review_state(state, data_root=data_root)
    write_verified_drafts(state, data_root=data_root)
    return state


def _candidate_by_id(state: ReviewState, candidate_id: str) -> ReviewCandidate:
    for candidate in state.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise VerificationError(f"Unknown candidate: {candidate_id}")


def _resync_question_passage_links(
    state: ReviewState,
    old_passage_id: str | None,
    new_passage_id: str | None,
    start_question: int | None,
    end_question: int | None,
) -> None:
    if not old_passage_id or not new_passage_id or old_passage_id == new_passage_id:
        return
    for index, candidate in enumerate(state.candidates):
        if candidate.candidate_type != CandidateType.QUESTION or candidate.passage_id != old_passage_id:
            continue
        patch = candidate.model_dump()
        patch["passage_id"] = new_passage_id
        patch["start_question"] = start_question
        patch["end_question"] = end_question
        state.candidates[index] = ReviewCandidate.model_validate(patch)


def update_candidate(
    exam_id: str,
    candidate_id: str,
    updates: dict[str, Any],
    *,
    data_root: Path = Path("data"),
) -> ReviewCandidate:
    """Apply UI updates to one candidate and rewrite staged drafts."""

    with _review_state_lock:
        state = load_review_state(exam_id, data_root=data_root)
        candidate = _candidate_by_id(state, candidate_id)
        old_passage_id = None
        if candidate.candidate_type == CandidateType.PASSAGE and candidate.start_question and candidate.end_question:
            old_passage_id = passage_id_for(exam_id, candidate.start_question, candidate.end_question)
        allowed = {
            "status",
            "verified_text",
            "stem",
            "choices",
            "correct_answer",
            "passage_id",
            "notes",
            "question_number",
            "start_question",
            "end_question",
        }
        patch = candidate.model_dump()
        for key, value in updates.items():
            if key in allowed:
                patch[key] = value
        updated = ReviewCandidate.model_validate(patch)
        if any(
            key in updates and getattr(updated, key) != getattr(candidate, key)
            for key in _OCR_DRAFT_EDITABLE_FIELDS
        ):
            updated = updated.model_copy(update={"manually_edited": True})
        index = state.candidates.index(candidate)
        state.candidates[index] = updated
        if updated.candidate_type == CandidateType.PASSAGE and updated.start_question and updated.end_question:
            new_passage_id = passage_id_for(exam_id, updated.start_question, updated.end_question)
            _resync_question_passage_links(
                state,
                old_passage_id,
                new_passage_id,
                updated.start_question,
                updated.end_question,
            )
        drafts = build_verified_drafts(state)
        save_review_state(state, data_root=data_root)
        write_verified_drafts(state, data_root=data_root, drafts=drafts)
        return updated


def reapply_ocr_draft(
    exam_id: str,
    candidate_id: str,
    *,
    data_root: Path = Path("data"),
) -> ReviewCandidate:
    """Explicitly replace editable fields with the stored OCR draft strategy."""

    with _review_state_lock:
        state = load_review_state(exam_id, data_root=data_root)
        candidate = _candidate_by_id(state, candidate_id)
        options = DraftOptions.model_validate(state.draft_options)
        updated = apply_ocr_draft(candidate, options, cleanup_backends=build_cleanup_backends(options))
        updated = updated.model_copy(update={"manually_edited": False})
        index = state.candidates.index(candidate)
        state.candidates[index] = updated
        drafts = build_verified_drafts(state)
        save_review_state(state, data_root=data_root)
        write_verified_drafts(state, data_root=data_root, drafts=drafts)
        return updated


def _passage_draft_from_candidate(exam_id: str, candidate: ReviewCandidate) -> VerifiedPassageDraft | None:
    if candidate.candidate_type != CandidateType.PASSAGE or candidate.status != ReviewStatus.ACCEPTED:
        return None
    if not candidate.start_question or not candidate.end_question:
        raise VerificationError(f"Accepted passage {candidate.candidate_id} is missing a question range.")
    body_text = candidate.verified_text.strip()
    if not body_text:
        raise VerificationError(f"Accepted passage {candidate.candidate_id} is missing verified text.")
    return VerifiedPassageDraft(
        id=passage_id_for(exam_id, candidate.start_question, candidate.end_question),
        exam_id=exam_id,
        passage_no=candidate.start_question,
        question_range=(candidate.start_question, candidate.end_question),
        body_text=body_text,
        source_provenance=candidate.provenance,
    )


def _question_draft_from_candidate(exam_id: str, candidate: ReviewCandidate) -> VerifiedQuestionDraft | None:
    if candidate.candidate_type != CandidateType.QUESTION or candidate.status != ReviewStatus.ACCEPTED:
        return None
    if not candidate.question_number:
        raise VerificationError(f"Accepted question {candidate.candidate_id} is missing a question number.")
    if candidate.correct_answer is None:
        raise VerificationError(f"Accepted question {candidate.candidate_id} is missing a correct answer.")
    stem = (candidate.stem or candidate.verified_text).strip()
    if not stem:
        raise VerificationError(f"Accepted question {candidate.candidate_id} is missing verified text.")
    choices = [
        Choice(choice_no=index, text=text.strip(), is_correct=index == candidate.correct_answer)
        for index, text in enumerate(candidate.choices, start=1)
    ]
    return VerifiedQuestionDraft(
        id=question_id_for(exam_id, candidate.question_number),
        exam_id=exam_id,
        question_no=candidate.question_number,
        passage_id=candidate.passage_id,
        stem=stem,
        choices=choices,
        correct_answer=candidate.correct_answer,
        source_provenance=candidate.provenance,
    )


def build_verified_drafts(state: ReviewState) -> tuple[list[VerifiedPassageDraft], list[VerifiedQuestionDraft]]:
    passages: list[VerifiedPassageDraft] = []
    questions: list[VerifiedQuestionDraft] = []
    for candidate in state.candidates:
        passage = _passage_draft_from_candidate(state.exam_id, candidate)
        if passage is not None:
            passages.append(passage)
        question = _question_draft_from_candidate(state.exam_id, candidate)
        if question is not None:
            questions.append(question)
    return passages, questions


def write_verified_drafts(
    state: ReviewState,
    *,
    data_root: Path = Path("data"),
    drafts: tuple[list[VerifiedPassageDraft], list[VerifiedQuestionDraft]] | None = None,
) -> tuple[Path, Path]:
    passages, questions = drafts if drafts is not None else build_verified_drafts(state)
    passage_path = passage_drafts_path(state.exam_id, data_root=data_root)
    question_path = question_drafts_path(state.exam_id, data_root=data_root)
    _write_jsonl(passage_path, passages)
    _write_jsonl(question_path, questions)
    return passage_path, question_path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise VerificationError(f"Invalid JSONL at {path}:{line_no}") from exc
    return rows


def load_verified_drafts(
    exam_id: str,
    *,
    data_root: Path = Path("data"),
) -> tuple[list[VerifiedPassageDraft], list[VerifiedQuestionDraft]]:
    try:
        passages = [VerifiedPassageDraft.model_validate(row) for row in _read_jsonl(passage_drafts_path(exam_id, data_root=data_root))]
        questions = [VerifiedQuestionDraft.model_validate(row) for row in _read_jsonl(question_drafts_path(exam_id, data_root=data_root))]
    except ValidationError as exc:
        raise VerificationError(str(exc)) from exc
    return passages, questions


def validate_promotion(passages: list[VerifiedPassageDraft], questions: list[VerifiedQuestionDraft]) -> None:
    errors: list[str] = []
    passage_ids = {passage.id for passage in passages}
    question_numbers: set[int] = set()
    for passage in passages:
        if not passage.source_provenance:
            errors.append(f"Passage {passage.id} is missing source provenance.")
    for question in questions:
        if question.question_no in question_numbers:
            errors.append(f"Duplicate question number: {question.question_no}.")
        question_numbers.add(question.question_no)
        if len(question.choices) != 5:
            errors.append(f"Question {question.question_no} must have exactly five choices.")
        if any(not (choice.text or "").strip() for choice in question.choices):
            errors.append(f"Question {question.question_no} has an empty choice.")
        if not 1 <= question.correct_answer <= 5:
            errors.append(f"Question {question.question_no} has an invalid correct answer.")
        if question.passage_id and question.passage_id not in passage_ids:
            errors.append(f"Question {question.question_no} links to missing passage {question.passage_id}.")
        if not question.source_provenance:
            errors.append(f"Question {question.question_no} is missing source provenance.")
    if errors:
        raise VerificationError("\n".join(errors))


def promote_verified(exam_id: str, *, data_root: Path = Path("data")) -> tuple[Path, Path, int, int]:
    passages, questions = load_verified_drafts(exam_id, data_root=data_root)
    validate_promotion(passages, questions)
    out_dir = canonical_dir(exam_id, data_root=data_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    passage_path = out_dir / "passages.jsonl"
    question_path = out_dir / "questions.jsonl"
    _write_jsonl_atomic(passage_path, passages)
    _write_jsonl_atomic(question_path, questions)
    return passage_path, question_path, len(passages), len(questions)


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(
    handler: BaseHTTPRequestHandler,
    body: str,
    *,
    status: HTTPStatus = HTTPStatus.OK,
    content_type: str = "text/html; charset=utf-8",
) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def workbench_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LEET Verification Workbench</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #f5f5f2; color: #202124; }
    header { height: 48px; display: flex; align-items: center; gap: 12px; padding: 0 16px; background: #263238; color: #fff; }
    main { display: grid; grid-template-columns: 280px minmax(340px, 1fr) 380px; height: calc(100vh - 48px); }
    aside, section { min-width: 0; overflow: auto; }
    aside { border-right: 1px solid #d0d0cc; background: #fff; }
    .filters { display: flex; gap: 6px; flex-wrap: wrap; padding: 10px; border-bottom: 1px solid #e0e0dc; }
    button, select, input, textarea { font: inherit; }
    button { border: 1px solid #9aa0a6; background: #fff; border-radius: 6px; padding: 6px 9px; cursor: pointer; }
    button.active { background: #2f5d62; color: #fff; border-color: #2f5d62; }
    .candidate { width: 100%; text-align: left; border: 0; border-bottom: 1px solid #eee; border-radius: 0; padding: 10px; }
    .candidate strong { display: block; }
    .candidate span { color: #5f6368; font-size: 12px; }
    .source { padding: 14px; background: #ebe9e2; }
    .source img { max-width: 100%; transform-origin: top left; background: white; border: 1px solid #d0d0cc; }
    .toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
    .editor { border-left: 1px solid #d0d0cc; background: #fff; padding: 14px; }
    label { display: block; font-size: 12px; color: #5f6368; margin: 10px 0 4px; }
    textarea { width: 100%; min-height: 86px; resize: vertical; }
    input, select { width: 100%; padding: 6px; }
    .choices { display: grid; gap: 6px; }
    .status { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 12px; }
    .hidden { display: none; }
    .field-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .draft-box { background: #fff8e1; border: 1px solid #e4c66a; border-radius: 6px; padding: 8px; margin-top: 10px; font-size: 12px; }
    .draft-box ul { margin: 6px 0 0 18px; padding: 0; }
    pre { white-space: pre-wrap; background: #f1f3f4; padding: 8px; border-radius: 6px; max-height: 160px; overflow: auto; }
  </style>
</head>
<body>
  <header><strong>LEET Verification Workbench</strong><span id="exam"></span></header>
  <main>
    <aside>
      <div class="filters" id="filters"></div>
      <div id="queue"></div>
    </aside>
    <section class="source">
      <div class="toolbar">
        <button id="zoomOut">-</button><button id="zoomIn">+</button><span id="title"></span>
      </div>
      <img id="preview" alt="candidate preview">
    </section>
    <section class="editor">
      <label>Status</label><select id="status"></select>
      <div id="passageFields">
        <label>Start question</label><input id="start_question" type="number" min="1">
        <label>End question</label><input id="end_question" type="number" min="1">
        <label>Passage body</label><textarea id="verified_text"></textarea>
      </div>
      <div id="questionFields">
        <label>Question number</label><input id="question_number" type="number" min="1">
        <label>Question stem</label><textarea id="stem"></textarea>
        <div class="choices" id="choices"></div>
        <label>Correct answer</label><input id="correct_answer" type="number" min="1" max="5">
        <label>Passage ID</label><input id="passage_id">
      </div>
      <label>Notes</label><textarea id="notes"></textarea>
      <div class="draft-box" id="draftBox"></div>
      <div class="status"><button id="applyDraft" type="button">Apply OCR draft</button><button id="save">Save</button><button id="next">Next</button></div>
      <div class="field-head"><label>Raw OCR</label><button id="copyRaw" type="button">Copy</button></div><pre id="raw"></pre>
      <label>Provenance</label><pre id="prov"></pre>
    </section>
  </main>
  <script>
    const statuses = ["unreviewed", "accepted", "needs_fix", "rejected"];
    let state, current, filter = "all", zoom = 1, autosaveTimer;
    async function load() {
      state = await fetch("/api/state").then(r => r.json());
      document.getElementById("exam").textContent = state.exam_id;
      renderFilters(); renderQueue();
      select(state.candidates[0]?.candidate_id);
    }
    function renderFilters() {
      const box = document.getElementById("filters"); box.innerHTML = "";
      ["all", ...statuses].forEach(s => {
        const b = document.createElement("button"); b.textContent = s; b.className = filter === s ? "active" : "";
        b.onclick = () => { filter = s; renderFilters(); renderQueue(); };
        box.appendChild(b);
      });
    }
    function renderQueue() {
      const q = document.getElementById("queue"); q.innerHTML = "";
      state.candidates.filter(c => filter === "all" || c.status === filter).forEach(c => {
        const b = document.createElement("button"); b.className = "candidate";
        const strong = document.createElement("strong"); strong.textContent = c.suggestion_id;
        const span = document.createElement("span"); span.textContent = `${c.candidate_type} - ${c.status}`;
        b.append(strong, span);
        b.onclick = () => select(c.candidate_id); q.appendChild(b);
      });
    }
    function setChoices(values) {
      const box = document.getElementById("choices"); box.innerHTML = "";
      for (let i = 0; i < 5; i++) {
        const input = document.createElement("input"); input.id = `choice_${i}`; input.placeholder = `Choice ${i + 1}`;
        input.value = values?.[i] || "";
        input.addEventListener("input", scheduleAutosave);
        box.appendChild(input);
      }
    }
    function setPanelMode(candidate) {
      const isPassage = candidate?.candidate_type === "passage";
      document.getElementById("passageFields").classList.toggle("hidden", !isPassage);
      document.getElementById("questionFields").classList.toggle("hidden", isPassage);
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
    }
    function select(id) {
      current = state.candidates.find(c => c.candidate_id === id); if (!current) return;
      setPanelMode(current);
      document.getElementById("title").textContent = current.suggestion_id;
      document.getElementById("preview").src = `/preview/${encodeURIComponent(current.candidate_id)}`;
      document.getElementById("status").innerHTML = statuses.map(s => `<option value="${s}">${s}</option>`).join("");
      document.getElementById("status").value = current.status;
      ["verified_text", "stem", "correct_answer", "passage_id", "notes", "question_number", "start_question", "end_question"].forEach(id => document.getElementById(id).value = current[id] || "");
      setChoices(current.choices);
      document.getElementById("raw").textContent = current.raw_ocr_text || "";
      document.getElementById("prov").textContent = JSON.stringify(current.provenance, null, 2);
      renderDraftMetadata();
    }
    function renderDraftMetadata() {
      const box = document.getElementById("draftBox");
      const warnings = current?.prefill_warnings || [];
      const steps = current?.correction_steps || [];
      const source = escapeHtml(current?.prefill_source || "none");
      const warningItems = warnings.map(item => `<li>${escapeHtml(item)}</li>`).join("");
      const stepItems = steps.map(item => `<li>${escapeHtml(item)}</li>`).join("");
      box.innerHTML = `<strong>OCR draft</strong><div>source: ${source}</div>` +
        (warnings.length ? `<div>warnings:<ul>${warningItems}</ul></div>` : "<div>warnings: none</div>") +
        (steps.length ? `<div>steps:<ul>${stepItems}</ul></div>` : "");
    }
    function numberValue(id) {
      const value = document.getElementById(id).value;
      return value ? Number(value) : null;
    }
    function editableFormValues(candidate) {
      if (candidate?.candidate_type === "passage") {
        return {verified_text: document.getElementById("verified_text").value};
      }
      return {
        stem: document.getElementById("stem").value,
        choices: [0,1,2,3,4].map(i => document.getElementById(`choice_${i}`).value)
      };
    }
    function hasUnsavedEditableEdits(candidate) {
      const values = editableFormValues(candidate);
      if (candidate?.candidate_type === "passage") {
        return values.verified_text !== (candidate.verified_text || "");
      }
      const savedChoices = candidate?.choices || [];
      return values.stem !== (candidate?.stem || "") || values.choices.some((value, index) => value !== (savedChoices[index] || ""));
    }
    function scheduleAutosave() {
      clearTimeout(autosaveTimer);
      autosaveTimer = setTimeout(() => save({reload: false}), 700);
    }
    async function save(options = {}) {
      if (!current) return;
      const reload = options.reload ?? true;
      const candidateId = current.candidate_id;
      let body = {
        status: document.getElementById("status").value,
        notes: document.getElementById("notes").value
      };
      if (current.candidate_type === "passage") {
        body = {
          ...body,
          verified_text: document.getElementById("verified_text").value,
          start_question: numberValue("start_question"),
          end_question: numberValue("end_question")
        };
      } else {
        body = {
          ...body,
          question_number: numberValue("question_number"),
          stem: document.getElementById("stem").value,
          choices: [0,1,2,3,4].map(i => document.getElementById(`choice_${i}`).value),
          correct_answer: numberValue("correct_answer"),
          passage_id: document.getElementById("passage_id").value || null
        };
      }
      const response = await fetch(`/api/candidates/${encodeURIComponent(candidateId)}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (!response.ok) return;
      const updated = await response.json();
      const index = state.candidates.findIndex(c => c.candidate_id === candidateId);
      if (index >= 0) state.candidates[index] = updated;
      current = updated;
      renderQueue();
      if (reload) {
        await load();
        select(candidateId);
      }
    }
    document.getElementById("save").onclick = save;
    document.getElementById("applyDraft").onclick = async () => {
      if (!current) return;
      clearTimeout(autosaveTimer);
      autosaveTimer = null;
      const hasEdits = current.manually_edited || hasUnsavedEditableEdits(current);
      if (hasEdits && !confirm("Replace current editable fields with the OCR draft?")) return;
      const candidateId = current.candidate_id;
      const response = await fetch(`/api/candidates/${encodeURIComponent(candidateId)}/apply-ocr-draft`, {method: "POST"});
      if (!response.ok) return;
      await load();
      select(candidateId);
    };
    ["status", "verified_text", "stem", "correct_answer", "passage_id", "notes", "question_number", "start_question", "end_question"].forEach(id => {
      const element = document.getElementById(id);
      element.addEventListener("input", scheduleAutosave);
      element.addEventListener("change", scheduleAutosave);
    });
    document.getElementById("next").onclick = () => {
      const list = state.candidates; const i = list.findIndex(c => c.candidate_id === current?.candidate_id);
      select(list[(i + 1) % list.length]?.candidate_id);
    };
    document.getElementById("zoomIn").onclick = () => { zoom += 0.1; document.getElementById("preview").style.transform = `scale(${zoom})`; };
    document.getElementById("zoomOut").onclick = () => { zoom = Math.max(0.3, zoom - 0.1); document.getElementById("preview").style.transform = `scale(${zoom})`; };
    document.getElementById("copyRaw").onclick = async () => {
      const text = document.getElementById("raw").textContent || "";
      const button = document.getElementById("copyRaw");
      const temp = document.createElement("textarea");
      temp.value = text;
      temp.setAttribute("readonly", "");
      temp.style.position = "fixed";
      temp.style.left = "-9999px";
      document.body.appendChild(temp);
      temp.select();
      document.execCommand("copy");
      temp.remove();
      button.textContent = "Copied";
      setTimeout(() => { button.textContent = "Copy"; }, 900);
    };
    load();
  </script>
</body>
</html>"""


class VerificationWorkbench:
    """Local HTTP workbench server wrapper."""

    def __init__(self, exam_id: str, *, data_root: Path = Path("data")) -> None:
        self.exam_id = exam_id
        self.data_root = data_root

    def handler_class(self) -> type[BaseHTTPRequestHandler]:
        workbench = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    _text_response(self, workbench_html())
                    return
                if parsed.path == "/api/state":
                    state = load_review_state(workbench.exam_id, data_root=workbench.data_root)
                    _json_response(self, state.model_dump(mode="json"))
                    return
                if parsed.path.startswith("/preview/"):
                    candidate_id = unquote(parsed.path.removeprefix("/preview/"))
                    workbench.serve_preview(self, candidate_id)
                    return
                _json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/candidates/"):
                    suffix = parsed.path.removeprefix("/api/candidates/")
                    if suffix.endswith("/apply-ocr-draft"):
                        candidate_id = unquote(suffix.removesuffix("/apply-ocr-draft"))
                        try:
                            candidate = reapply_ocr_draft(
                                workbench.exam_id,
                                candidate_id,
                                data_root=workbench.data_root,
                            )
                        except (ValidationError, VerificationError) as exc:
                            _json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                            return
                        _json_response(self, candidate.model_dump(mode="json"))
                        return
                    candidate_id = unquote(suffix)
                    length = int(self.headers.get("Content-Length") or 0)
                    body = self.rfile.read(length).decode("utf-8")
                    try:
                        payload = json.loads(body) if body else {}
                        candidate = update_candidate(
                            workbench.exam_id,
                            candidate_id,
                            payload,
                            data_root=workbench.data_root,
                        )
                    except (json.JSONDecodeError, ValidationError, VerificationError) as exc:
                        _json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                        return
                    _json_response(self, candidate.model_dump(mode="json"))
                    return
                _json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

        return Handler

    def serve_preview(self, handler: BaseHTTPRequestHandler, candidate_id: str) -> None:
        state = load_review_state(self.exam_id, data_root=self.data_root)
        candidate = _candidate_by_id(state, candidate_id)
        if not candidate.preview_path:
            _json_response(handler, {"error": "candidate has no preview"}, HTTPStatus.NOT_FOUND)
            return
        path = Path(candidate.preview_path).resolve()
        suggestions_root = Path(state.suggestions_path).resolve().parent
        if _is_relative_to(path, suggestions_root) and not (path.exists() and path.is_file()):
            original_path = candidate.provenance.get("original", {}).get("candidate_preview_path")
            try:
                resolved_original = _resolve_artifact_path(original_path, suggestions_root)
            except VerificationError:
                resolved_original = None
            if resolved_original:
                path = Path(resolved_original).resolve()
        if not _is_relative_to(path, suggestions_root) or not path.exists() or not path.is_file():
            _json_response(handler, {"error": "preview not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)


def create_review_server(
    exam_id: str,
    *,
    data_root: Path = Path("data"),
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    workbench = VerificationWorkbench(exam_id, data_root=data_root)
    return ThreadingHTTPServer((host, port), workbench.handler_class())


def serve_review_workbench(
    exam_id: str,
    *,
    data_root: Path = Path("data"),
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> str:
    server = create_review_server(exam_id, data_root=data_root, host=host, port=port)
    url = f"http://{server.server_address[0]}:{server.server_address[1]}/"
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return url
