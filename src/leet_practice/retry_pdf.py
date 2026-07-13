"""Create printable retry workbooks from tagged wrong-answer records."""

from __future__ import annotations

import html
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from leet_practice.retry_results import (
    RetryOutcome,
    RetryQuestionStatus,
    RetryResultError,
    load_latest_retry_statuses,
)


DEFAULT_DATA_ROOT = Path("data")
DEFAULT_LIMIT = 20
DEFAULT_TITLE = "LEET 오답 재풀이"
DEFAULT_OUTPUT_DIR = Path("output/pdf/retry-pdfs")
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


class RetryPdfError(RuntimeError):
    """Raised when a retry workbook cannot be selected or generated."""


@dataclass(frozen=True)
class RetryQuestionContext:
    """A selected tagged review hydrated with canonical question text."""

    review_file: str
    exam_id: str
    year: int | None
    section: str | None
    question_no: int
    question_id: str | None
    canonical_exam_id: str
    canonical_dir: str
    passage_id: str | None
    passage_text: str | None
    stem: str
    choices: tuple[tuple[int, str], ...]
    selected_choice: int | None
    correct_choice: int
    primary_tag: str
    secondary_tags: tuple[str, ...]
    tag_confidence: str | None
    tag_rationale: str | None
    revisit_plan: str | None


@dataclass(frozen=True)
class RetryPdfBundle:
    """Paths and selection details produced by one workbook generation."""

    session_id: str
    pdf_path: Path
    manifest_path: Path
    selected: list[RetryQuestionContext]
    skipped: list[dict[str, str]]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RetryPdfError(f"Required JSONL file not found: {path}")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RetryPdfError(f"Invalid JSON in {path} at line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise RetryPdfError(f"Expected an object in {path} at line {line_no}")
        rows.append(row)
    return rows


def load_tagging_records(*, data_root: Path = DEFAULT_DATA_ROOT) -> list[dict[str, Any]]:
    """Load the provisional wrong-answer tagging corpus."""

    return _read_jsonl(Path(data_root) / "tagging" / "provisional_tags.jsonl")


def _normalized_review_file(value: str | Path, *, data_root: Path) -> str:
    raw = Path(value)
    if raw.is_absolute():
        try:
            return raw.resolve().relative_to(data_root.resolve().parent).as_posix()
        except ValueError:
            return raw.resolve().as_posix()
    return raw.as_posix().lstrip("./")


def _record_review_key(record: dict[str, Any], *, data_root: Path) -> str:
    return _normalized_review_file(str(record.get("review_file") or ""), data_root=data_root)


def _record_tags(record: dict[str, Any]) -> tuple[str, tuple[str, ...], str | None]:
    tags = record.get("provisional_tags") or {}
    primary = str(tags.get("primary") or "UNTAGGED")
    secondary = tuple(str(tag) for tag in (tags.get("secondary") or []) if tag)
    confidence = str(tags.get("confidence")) if tags.get("confidence") else None
    return primary, secondary, confidence


def _eligible_record(
    record: dict[str, Any],
    *,
    tags: set[str],
    years: set[int],
    sections: set[str],
    include_holdout: bool,
) -> bool:
    if record.get("is_correct") is True:
        return False
    if record.get("holdout") and not include_holdout:
        return False
    primary, secondary, _ = _record_tags(record)
    if tags and not ({primary, *secondary} & tags):
        return False
    try:
        record_year = int(record["year"]) if record.get("year") is not None else None
    except (TypeError, ValueError):
        record_year = None
    if years and record_year not in years:
        return False
    if sections and str(record.get("section") or "") not in sections:
        return False
    return True


def _review_input_sort_key(record: dict[str, Any]) -> tuple[int, float]:
    value = record.get("review_input_at")
    if not value:
        return (1, 0.0)
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return (1, 0.0)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (0, parsed.astimezone(timezone.utc).timestamp())


def _record_sort_key(record: dict[str, Any]) -> tuple[int, float, int, int, str, int, str]:
    _, _, confidence = _record_tags(record)
    try:
        year = int(record.get("year") or 9999)
    except (TypeError, ValueError):
        year = 9999
    try:
        question_no = int(record.get("question_no") or 0)
    except (TypeError, ValueError):
        question_no = 0
    return (
        *_review_input_sort_key(record),
        CONFIDENCE_ORDER.get(str(confidence or "").lower(), 3),
        year,
        str(record.get("section") or ""),
        question_no,
        str(record.get("review_file") or ""),
    )


def _effective_retry_outcome(
    record: dict[str, Any],
    status: RetryQuestionStatus | None,
) -> RetryOutcome | None:
    if status is None:
        return None
    if status.last_selected_choice is None:
        return RetryOutcome.SKIPPED
    try:
        current_correct = int(record.get("correct_choice"))
    except (TypeError, ValueError):
        current_correct = status.correct_choice
    return (
        RetryOutcome.CORRECT
        if status.last_selected_choice == current_correct
        else RetryOutcome.INCORRECT
    )


def _history_tier(
    record: dict[str, Any],
    *,
    data_root: Path,
    retry_statuses: Mapping[str, RetryQuestionStatus],
) -> int:
    outcome = _effective_retry_outcome(
        record,
        retry_statuses.get(_record_review_key(record, data_root=data_root)),
    )
    if outcome is RetryOutcome.INCORRECT:
        return 0
    if outcome is RetryOutcome.SKIPPED:
        return 1
    if outcome is None:
        return 2
    return 3


def _balanced_selection(
    records: Sequence[dict[str, Any]],
    *,
    limit: int,
    weakness_counts: Counter[str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_record_tags(record)[0]].append(record)
    for group in grouped.values():
        group.sort(key=_record_sort_key)
    ordered_tags = sorted(grouped, key=lambda tag: (-weakness_counts.get(tag, 0), tag))
    selected: list[dict[str, Any]] = []
    while len(selected) < limit:
        added = False
        for primary_tag in ordered_tags:
            if grouped[primary_tag]:
                selected.append(grouped[primary_tag].pop(0))
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
    if any(_review_input_sort_key(record)[0] == 0 for record in selected):
        selected.sort(key=_record_sort_key)
    return selected


def select_retry_questions(
    records: Sequence[dict[str, Any]],
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
    review_files: Sequence[str | Path] | None = None,
    limit: int = DEFAULT_LIMIT,
    tags: Sequence[str] | None = None,
    years: Sequence[int] | None = None,
    sections: Sequence[str] | None = None,
    include_holdout: bool = False,
    retry_statuses: Mapping[str, RetryQuestionStatus] | None = None,
    include_completed: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Select records explicitly or via deterministic, tag-balanced ranking."""

    if limit < 1:
        raise RetryPdfError("limit must be at least 1")
    tag_filter = {str(tag) for tag in (tags or []) if tag}
    year_filter = {int(year) for year in (years or [])}
    section_filter = {str(section) for section in (sections or []) if section}
    retry_statuses = retry_statuses or {}
    base_eligible = [
        record
        for record in records
        if _eligible_record(
            record,
            tags=tag_filter,
            years=year_filter,
            sections=section_filter,
            include_holdout=include_holdout,
        )
    ]
    eligible = [
        record
        for record in base_eligible
        if include_completed
        or _history_tier(record, data_root=data_root, retry_statuses=retry_statuses) != 3
    ]
    skipped: list[dict[str, str]] = []

    if review_files:
        all_by_key = {_record_review_key(record, data_root=data_root): record for record in records}
        base_eligible_keys = {_record_review_key(record, data_root=data_root) for record in base_eligible}
        eligible_keys = {_record_review_key(record, data_root=data_root) for record in eligible}
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for requested in review_files:
            key = _normalized_review_file(requested, data_root=data_root)
            record = all_by_key.get(key)
            if record is None and Path(key).is_absolute():
                matches = [candidate for candidate in all_by_key if key.endswith(candidate)]
                record = all_by_key[matches[0]] if len(matches) == 1 else None
                key = matches[0] if len(matches) == 1 else key
            if record is None:
                skipped.append({"review_file": key, "reason": "tagging record not found"})
            elif key not in base_eligible_keys:
                skipped.append({"review_file": key, "reason": "excluded by filters or holdout policy"})
            elif key not in eligible_keys:
                skipped.append(
                    {
                        "review_file": key,
                        "reason": "latest retry result is correct; pass include_completed to include it",
                    }
                )
            elif key not in seen:
                selected.append(record)
                seen.add(key)
        return selected, skipped

    # Weakness is measured over active, non-holdout wrong answers before the
    # user's display filters narrow the candidate pool.
    weakness_counts = Counter(
        _record_tags(record)[0]
        for record in records
        if record.get("is_correct") is not True
        and not record.get("holdout")
        and record.get("use_for_tag_frequency", True)
    )
    selected: list[dict[str, Any]] = []
    tier_order = (0, 1, 2, 3) if include_completed else (0, 1, 2)
    for tier in tier_order:
        remaining = limit - len(selected)
        if remaining <= 0:
            break
        tier_records = [
            record
            for record in eligible
            if _history_tier(record, data_root=data_root, retry_statuses=retry_statuses) == tier
        ]
        selected.extend(
            _balanced_selection(tier_records, limit=remaining, weakness_counts=weakness_counts)
        )
    return selected, skipped


def _section_family(value: str | None) -> str | None:
    text = str(value or "")
    if "언어" in text:
        return "언어이해"
    if "추리" in text:
        return "추리논증"
    return text or None


def _year_from_text(value: str | None) -> int | None:
    match = re.search(r"\b(20\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else None


def _canonical_index(data_root: Path) -> list[dict[str, Any]]:
    canonical_root = data_root / "canonical"
    if not canonical_root.is_dir():
        raise RetryPdfError(f"Canonical data directory not found: {canonical_root}")
    indexed: list[dict[str, Any]] = []
    for directory in sorted(path for path in canonical_root.iterdir() if path.is_dir()):
        questions_path = directory / "questions.jsonl"
        if not questions_path.is_file():
            continue
        passages: dict[str, dict[str, Any]] = {}
        passages_path = directory / "passages.jsonl"
        if passages_path.is_file():
            for passage in _read_jsonl(passages_path):
                if passage.get("id"):
                    passages[str(passage["id"])] = passage
        for question in _read_jsonl(questions_path):
            exam_id = str(question.get("exam_id") or directory.name)
            indexed.append(
                {
                    "directory": directory,
                    "directory_name": directory.name,
                    "exam_id": exam_id,
                    "year": _year_from_text(exam_id) or _year_from_text(directory.name),
                    "section": _section_family(exam_id) or _section_family(directory.name),
                    "question": question,
                    "passage": passages.get(str(question.get("passage_id"))),
                }
            )
    return indexed


def _resolve_review_path(review_file: str, *, data_root: Path) -> Path:
    raw = Path(review_file)
    if raw.is_absolute():
        path = raw.resolve()
    else:
        parts = raw.parts
        if parts and parts[0].lower() == data_root.name.lower():
            path = (data_root.parent / raw).resolve()
        elif parts and parts[0].lower() == "data":
            path = (data_root / Path(*parts[1:])).resolve()
        elif parts and parts[0].lower() == "reviews":
            path = (data_root / raw).resolve()
        else:
            path = (data_root.parent / raw).resolve()
    review_root = (data_root / "reviews").resolve()
    if not path.is_relative_to(review_root):
        raise RetryPdfError(f"Review file must be under {review_root}: {review_file}")
    if not path.name.endswith(".review.json"):
        raise RetryPdfError(f"Review file must end with .review.json: {review_file}")
    return path


def _find_canonical_entry(record: dict[str, Any], index: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    question_id = str(record.get("question_id") or "")
    exact_id = [entry for entry in index if str(entry["question"].get("id") or "") == question_id]
    if len(exact_id) == 1:
        return exact_id[0]
    try:
        question_no = int(record.get("question_no"))
    except (TypeError, ValueError):
        return None
    year = int(record["year"]) if record.get("year") is not None else _year_from_text(str(record.get("exam_id")))
    section = _section_family(str(record.get("section") or record.get("exam_id") or ""))
    matches = [
        entry
        for entry in index
        if entry["question"].get("question_no") == question_no
        and entry["year"] == year
        and entry["section"] == section
    ]
    if len(matches) == 1:
        return matches[0]
    exam_id = str(record.get("exam_id") or "")
    exact_exam = [entry for entry in matches if entry["exam_id"] == exam_id or entry["directory_name"] == exam_id]
    return exact_exam[0] if len(exact_exam) == 1 else None


def _optional_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def load_retry_question_contexts(
    records: Sequence[dict[str, Any]],
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> tuple[list[RetryQuestionContext], list[dict[str, str]]]:
    """Hydrate selected tag records with review and canonical question data."""

    data_root = Path(data_root)
    index = _canonical_index(data_root)
    contexts: list[RetryQuestionContext] = []
    skipped: list[dict[str, str]] = []
    for record in records:
        review_file = str(record.get("review_file") or "")
        try:
            review_path = _resolve_review_path(review_file, data_root=data_root)
            if not review_path.is_file():
                raise RetryPdfError("review file not found")
            review = json.loads(review_path.read_text(encoding="utf-8"))
            canonical = _find_canonical_entry(record, index)
            if canonical is None:
                raise RetryPdfError("canonical question could not be matched")
            question = canonical["question"]
            stem = str(question.get("stem") or "").strip()
            choices = tuple(
                (int(choice["choice_no"]), str(choice.get("text") or "").strip())
                for choice in (question.get("choices") or [])
                if choice.get("choice_no") is not None
            )
            if not stem or not choices or any(not text for _, text in choices):
                raise RetryPdfError("canonical stem or choice text is incomplete")
            grading = review.get("grading") or {}
            correct_choice = int(question.get("correct_answer") or record.get("correct_choice") or grading.get("correct_choice"))
            selected_raw = record.get("selected_choice") or grading.get("selected_choice")
            primary, secondary, confidence = _record_tags(record)
            passage = canonical.get("passage") or {}
            contexts.append(
                RetryQuestionContext(
                    review_file=_record_review_key(record, data_root=data_root),
                    exam_id=str(record.get("exam_id") or review.get("exam_id") or canonical["exam_id"]),
                    year=int(record["year"]) if record.get("year") is not None else canonical["year"],
                    section=str(record.get("section")) if record.get("section") else canonical["section"],
                    question_no=int(record.get("question_no") or question["question_no"]),
                    question_id=str(question.get("id")) if question.get("id") else None,
                    canonical_exam_id=str(canonical["exam_id"]),
                    canonical_dir=str(canonical["directory"]),
                    passage_id=str(question.get("passage_id")) if question.get("passage_id") else None,
                    passage_text=_optional_text(passage.get("body_text") or passage.get("text") or passage.get("passage_text")),
                    stem=stem,
                    choices=choices,
                    selected_choice=int(selected_raw) if selected_raw is not None else None,
                    correct_choice=correct_choice,
                    primary_tag=primary,
                    secondary_tags=secondary,
                    tag_confidence=confidence,
                    tag_rationale=_optional_text(record.get("tag_rationale")),
                    revisit_plan=_optional_text(record.get("revisit_plan")),
                )
            )
        except (RetryPdfError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            skipped.append({"review_file": review_file, "reason": str(exc)})
    return _group_shared_passages(contexts), skipped


def _group_shared_passages(contexts: Sequence[RetryQuestionContext]) -> list[RetryQuestionContext]:
    """Move questions sharing a passage together while preserving first-seen groups."""

    order: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], list[RetryQuestionContext]] = defaultdict(list)
    for context in contexts:
        key = (
            context.canonical_dir,
            context.passage_id or f"__question_{context.question_no}_{context.review_file}",
        )
        if key not in groups:
            order.append(key)
        groups[key].append(context)
    return [context for key in order for context in groups[key]]


def discover_korean_font(font_path: Path | None = None) -> Path:
    """Find a Korean-capable font or validate an explicit font path."""

    if font_path is not None:
        candidate = Path(font_path).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        raise RetryPdfError(f"Font file not found: {candidate}")
    env_font = os.environ.get("LEET_PRACTICE_KOREAN_FONT")
    candidates = [
        Path(env_font).expanduser() if env_font else None,
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/NotoSansKR-Regular.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("/Library/Fonts/NotoSansCJKkr-Regular.otf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RetryPdfError(
        "No Korean font was found. Pass --font PATH or set LEET_PRACTICE_KOREAN_FONT "
        "to a Korean TrueType/OpenType font."
    )


def _paragraph_text(value: str) -> str:
    return html.escape(value).replace("\n", "<br/>")


def _pdf_styles(font_name: str) -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    common = {"fontName": font_name, "wordWrap": "CJK", "textColor": colors.HexColor("#172033")}
    return {
        "title": ParagraphStyle(
            "RetryTitle", parent=base["Title"], fontSize=24, leading=32, alignment=TA_CENTER, spaceAfter=16, **common
        ),
        "subtitle": ParagraphStyle(
            "RetrySubtitle", parent=base["Normal"], fontSize=10, leading=15, alignment=TA_CENTER,
            textColor=colors.HexColor("#667085"), fontName=font_name, wordWrap="CJK", spaceAfter=22,
        ),
        "section": ParagraphStyle(
            "RetrySection", parent=base["Heading1"], fontSize=18, leading=24, spaceBefore=8, spaceAfter=14,
            keepWithNext=True, **common
        ),
        "passage_heading": ParagraphStyle(
            "RetryPassageHeading", parent=base["Heading2"], fontSize=11, leading=16, spaceBefore=10,
            spaceAfter=7, textColor=colors.HexColor("#3730a3"), fontName=font_name, wordWrap="CJK",
        ),
        "question": ParagraphStyle(
            "RetryQuestion", parent=base["Heading2"], fontSize=12, leading=18, spaceBefore=14, spaceAfter=8,
            **common
        ),
        "body": ParagraphStyle(
            "RetryBody", parent=base["BodyText"], fontSize=9.4, leading=15, alignment=TA_LEFT, spaceAfter=7, **common
        ),
        "choice": ParagraphStyle(
            "RetryChoice", parent=base["BodyText"], fontSize=9.4, leading=14, leftIndent=9, firstLineIndent=-9,
            spaceAfter=5, **common
        ),
        "meta": ParagraphStyle(
            "RetryMeta", parent=base["BodyText"], fontSize=8.6, leading=13, textColor=colors.HexColor("#475467"),
            fontName=font_name, wordWrap="CJK", spaceAfter=5,
        ),
    }


def render_retry_pdf(
    contexts: Sequence[RetryQuestionContext],
    *,
    output_path: Path,
    title: str = DEFAULT_TITLE,
    font_path: Path | None = None,
    session_id: str | None = None,
) -> Path:
    """Render a problem-first workbook followed by a separate answer appendix."""

    if not contexts:
        raise RetryPdfError("No hydrated questions are available for PDF generation")
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import CondPageBreak, PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RetryPdfError("PDF generation requires the 'pdf' extra: pip install -e .[pdf]") from exc

    output_path = Path(output_path)
    if output_path.suffix.lower() != ".pdf":
        raise RetryPdfError("Output path must end with .pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_font = discover_korean_font(font_path)
    font_name = "LEETRetryKorean"
    try:
        pdfmetrics.registerFont(TTFont(font_name, str(resolved_font)))
    except Exception as exc:
        raise RetryPdfError(f"Could not load Korean font {resolved_font}: {exc}") from exc
    styles = _pdf_styles(font_name)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=19 * mm,
        bottomMargin=17 * mm,
        title=title,
        author="LEET Practice",
        subject="Wrong-answer retry workbook",
    )

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D0D5DD"))
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(18 * mm, 8.5 * mm, title)
        canvas.drawRightString(A4[0] - 18 * mm, 8.5 * mm, str(doc.page))
        canvas.restoreState()

    story: list[Any] = [
        Paragraph(_paragraph_text(title), styles["title"]),
        Paragraph(
            _paragraph_text(
                f"문항 수 {len(contexts)} - 정답과 분석은 뒤쪽 해설부에 있습니다."
                + (f" - 세션 {session_id}" if session_id else "")
            ),
            styles["subtitle"],
        ),
        Paragraph("문제", styles["section"]),
    ]
    previous_passage_key: tuple[str, str] | None = None
    for workbook_no, context in enumerate(contexts, start=1):
        passage_key = (context.canonical_dir, context.passage_id or f"question-{workbook_no}")
        if context.passage_text and passage_key != previous_passage_key:
            story.extend(
                [
                    CondPageBreak(25 * mm),
                    Paragraph(
                        _paragraph_text(f"지문 - {context.year or ''} {context.section or ''}".strip()),
                        styles["passage_heading"],
                    ),
                    Paragraph(_paragraph_text(context.passage_text), styles["body"]),
                    Spacer(1, 4),
                ]
            )
        previous_passage_key = passage_key
        label = f"{workbook_no}. {context.year or ''} {context.section or ''} 원문 {context.question_no}번".strip()
        story.append(CondPageBreak(35 * mm))
        story.append(Paragraph(_paragraph_text(label), styles["question"]))
        story.append(Paragraph(_paragraph_text(context.stem), styles["body"]))
        for choice_no, choice_text in context.choices:
            story.append(Paragraph(_paragraph_text(f"{choice_no}. {choice_text}"), styles["choice"]))
        story.append(Spacer(1, 8))

    story.extend([PageBreak(), Paragraph("정답 및 오답 분석", styles["section"])])
    for workbook_no, context in enumerate(contexts, start=1):
        story.append(CondPageBreak(35 * mm))
        story.append(
            Paragraph(
                _paragraph_text(
                    f"{workbook_no}. {context.year or ''} {context.section or ''} 원문 {context.question_no}번"
                ),
                styles["question"],
            )
        )
        selected = str(context.selected_choice) if context.selected_choice is not None else "기록 없음"
        story.append(
            Paragraph(
                _paragraph_text(f"정답 {context.correct_choice} - 기존 선택 {selected}"),
                styles["body"],
            )
        )
        secondary = ", ".join(context.secondary_tags) or "없음"
        story.append(
            Paragraph(
                _paragraph_text(
                    f"주요 태그: {context.primary_tag} / 보조 태그: {secondary} / 신뢰도: {context.tag_confidence or '미지정'}"
                ),
                styles["meta"],
            )
        )
        if context.tag_rationale:
            story.append(Paragraph(_paragraph_text(f"오답 분석: {context.tag_rationale}"), styles["body"]))
        if context.revisit_plan:
            story.append(Paragraph(_paragraph_text(f"재풀이 계획: {context.revisit_plan}"), styles["body"]))
        story.append(Spacer(1, 6))

    try:
        document.build(story, onFirstPage=footer, onLaterPages=footer)
    except Exception as exc:
        raise RetryPdfError(f"Failed to render PDF: {exc}") from exc
    return output_path


def _manifest_context(context: RetryQuestionContext) -> dict[str, Any]:
    return {
        "review_file": context.review_file,
        "exam_id": context.exam_id,
        "canonical_exam_id": context.canonical_exam_id,
        "question_id": context.question_id,
        "year": context.year,
        "section": context.section,
        "question_no": context.question_no,
        "passage_id": context.passage_id,
        "selected_choice": context.selected_choice,
        "correct_choice": context.correct_choice,
        "primary_tag": context.primary_tag,
        "secondary_tags": list(context.secondary_tags),
        "tag_confidence": context.tag_confidence,
    }


def _default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return DEFAULT_OUTPUT_DIR / f"retry-{stamp}.pdf"


def _new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"retry-{stamp}-{uuid.uuid4().hex[:10]}"


def create_retry_pdf_bundle(
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
    review_files: Sequence[str | Path] | None = None,
    limit: int = DEFAULT_LIMIT,
    tags: Sequence[str] | None = None,
    years: Sequence[int] | None = None,
    sections: Sequence[str] | None = None,
    include_holdout: bool = False,
    include_completed: bool = False,
    title: str = DEFAULT_TITLE,
    output_path: Path | None = None,
    font_path: Path | None = None,
) -> RetryPdfBundle:
    """Select, hydrate, render, and record one retry workbook bundle."""

    data_root = Path(data_root)
    records = load_tagging_records(data_root=data_root)
    try:
        retry_statuses = load_latest_retry_statuses(data_root=data_root)
    except RetryResultError as exc:
        raise RetryPdfError(f"Could not load retry history: {exc}") from exc
    selected_records, selection_skipped = select_retry_questions(
        records,
        data_root=data_root,
        review_files=review_files,
        limit=limit,
        tags=tags,
        years=years,
        sections=sections,
        include_holdout=include_holdout,
        retry_statuses=retry_statuses,
        include_completed=include_completed,
    )
    contexts, hydration_skipped = load_retry_question_contexts(selected_records, data_root=data_root)
    skipped = [*selection_skipped, *hydration_skipped]
    if not contexts:
        detail = f" ({len(skipped)} skipped)" if skipped else ""
        raise RetryPdfError(f"No selectable wrong-answer questions were found{detail}")
    session_id = _new_session_id()
    pdf_path = Path(output_path) if output_path is not None else _default_output_path()
    pdf_path = render_retry_pdf(
        contexts,
        output_path=pdf_path,
        title=title,
        font_path=font_path,
        session_id=session_id,
    )
    manifest_path = pdf_path.with_suffix(".json")
    tag_summary = Counter(context.primary_tag for context in contexts)
    payload = {
        "schema_version": 2,
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "settings": {
            "limit": limit,
            "tags": list(tags or []),
            "years": list(years or []),
            "sections": list(sections or []),
            "include_holdout": include_holdout,
            "include_completed": include_completed,
            "selection_mode": "explicit" if review_files else "recommended",
        },
        "pdf_path": str(pdf_path),
        "selected": [_manifest_context(context) for context in contexts],
        "tag_summary": dict(sorted(tag_summary.items())),
        "skipped": skipped,
    }
    try:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise RetryPdfError(f"PDF was created but manifest could not be written: {exc}") from exc
    return RetryPdfBundle(
        session_id=session_id,
        pdf_path=pdf_path,
        manifest_path=manifest_path,
        selected=list(contexts),
        skipped=skipped,
    )
