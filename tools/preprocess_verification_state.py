#!/usr/bin/env python3
"""Preprocess OCR-derived verification workbench state.

This helper is for exam-local verification data such as
`data/verification/2021 추리논증/crop-review-state.json`.

It does not verify official text. It only makes the review workbench easier to
use by re-splitting OCR text into a question stem and five choices, normalizing
common OCR marker errors such as `7` -> `ㄱ` and `L` -> `ㄴ` in 보기/choice
contexts, and marking imported candidates for visual review.

Example:
    python tools/preprocess_verification_state.py --exam-id "2021 추리논증" --dry-run
    python tools/preprocess_verification_state.py --exam-id "2021 추리논증" --set-status needs_fix
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DATA_ROOT = Path("data")
CIRCLED_TO_NO = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}
NO_TO_CIRCLED = {value: key for key, value in CIRCLED_TO_NO.items()}

# OCR often reads 보기 labels and answer-combination choices incorrectly.
MARKER_TRANSLATION = str.maketrans({"7": "ㄱ", "L": "ㄴ"})


@dataclass(frozen=True)
class SplitResult:
    stem: str
    choices: list[str]
    warnings: list[str]


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    # Keep intentional block boundaries around problem sections.
    kept: list[str] = []
    blank_pending = False
    for line in lines:
        if not line:
            blank_pending = True
            continue
        if blank_pending and kept and re.match(r"^<[^>]+>$", line):
            kept.append("")
        kept.append(line)
        blank_pending = False
    return "\n".join(kept).strip()


def normalize_common_ocr(text: str) -> str:
    """Apply conservative OCR fixes that are high-confidence in LEET drafts."""

    replacements = {
        "옮은": "옳은",
        "옮지": "옳지",
        "협오": "혐오",
        "플랫품": "플랫폼",
        "빛을": "빚을",
        "빛의": "빚의",
        "제도반대": "제도 반대",
        "제도를반대": "제도를 반대",
        "되어있다": "되어 있다",
        "있는대로": "있는 대로",
        "있는 대로고른": "있는 대로 고른",
        "<보기>": "<보 기>",
        "<보 기>": "<보 기>",
        "<논쟁>": "<논쟁>",
        "<규정>": "<규정>",
        "<사례>": "<사례>",
        "<이론>": "<이론>",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 보기 labels at line starts: 7./7, L./L, 드. are OCR errors for ㄱ/ㄴ/ㄷ.
    text = re.sub(r"(?m)^7(?=[\.,\s])", "ㄱ", text)
    text = re.sub(r"(?m)^L(?=[\.,\s])", "ㄴ", text)
    text = re.sub(r"(?m)^드(?=[\.,\s])", "ㄷ", text)
    text = re.sub(r"(?m)^([ㄱㄴㄷ])\s*\.\s*", r"\1. ", text)

    # Common OCR bullet variants in condition lists.
    text = re.sub(r"(?m)^[O0]\s+", "ㅇ ", text)
    text = re.sub(r"(?m)^[O0](?=[가-힣'‘\"<])", "ㅇ ", text)

    # Spacing around angle-bracket sections and punctuation.
    text = re.sub(r"(?<=[가-힣A-Za-z0-9)])<", "\n<", text)
    text = re.sub(r">(?=[가-힣A-Za-z0-9])", ">\n", text)
    text = re.sub(r"(?<=[가-힣A-Za-z0-9])\.\s*(?=[가-힣A-Za-z])", ". ", text)
    text = re.sub(r"(?<=[가-힣A-Za-z0-9]),\s*(?=[가-힣A-Za-z])", ", ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def strip_tail_artifacts(text: str) -> str:
    """Remove only terminal page/footer noise, preserving numeric diagram rows."""

    lines = text.split("\n")
    cutoff = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("* 확인 사항") or stripped.startswith("ㅇ문제지와 답안지"):
            cutoff = index
            break

    cleaned = lines[:cutoff]
    while cleaned:
        stripped = cleaned[-1].strip()
        if stripped in {"증", "드증", "ㄷ증"} or re.fullmatch(r"\d{1,2}", stripped):
            cleaned.pop()
            continue
        break
    return "\n".join(cleaned).strip()


def choice_marker(line: str) -> tuple[int | None, str]:
    stripped = line.strip()
    if not stripped:
        return None, ""

    first = stripped[0]
    if first in CIRCLED_TO_NO:
        return CIRCLED_TO_NO[first], stripped[1:].strip()

    # A bare digit at the beginning of a final answer choice is common OCR for
    # circled markers. Avoid article/section numbers such as 제1조 by only
    # accepting 1-5 at the very start of a line.
    match = re.match(r"^([1-5])\s*(.*)$", stripped)
    if match:
        return int(match.group(1)), match.group(2).strip()
    return None, stripped


def is_combo_choice(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    compact = compact.translate(MARKER_TRANSLATION).replace("드", "ㄷ")
    return bool(re.fullmatch(r"[ㄱㄴㄷ](,[ㄱㄴㄷ]){0,2}", compact))


def normalize_combo_choice(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    compact = compact.translate(MARKER_TRANSLATION).replace("드", "ㄷ")
    compact = compact.replace("，", ",")
    compact = re.sub(r",+", ",", compact).strip(",")
    if re.fullmatch(r"[ㄱㄴㄷ](,[ㄱㄴㄷ]){0,2}", compact):
        return ", ".join(compact.split(","))
    return text.strip()


def normalize_choice_text(text: str) -> str:
    text = strip_tail_artifacts(text)
    text = normalize_common_ocr(text)
    # If the choice is a pure answer-combination marker, normalize OCR labels.
    if is_combo_choice(text):
        return normalize_combo_choice(text)
    return join_wrapped_lines(text.split("\n"))


def join_wrapped_lines(lines: list[str]) -> str:
    result = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if not result:
            result = line
            continue
        # Preserve explicit section starts.
        if re.match(r"^<[^>]+>$", line) or re.match(r"^[ㄱㄴㄷ]\.", line):
            result += "\n" + line
        elif result.endswith((".", "?", "!", "다.", "요.", "군.")):
            result += "\n" + line
        else:
            result += " " + line
    return re.sub(r"[ \t]+", " ", result).strip()


def find_choice_positions(lines: list[str]) -> list[tuple[int, int, str]]:
    markers: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        number, rest = choice_marker(line)
        if number is not None:
            markers.append((idx, number, rest))

    # Find the last increasing 1..5 sequence. This protects against 제1조 and
    # numbered regulation clauses that appear in the stem.
    best: list[tuple[int, int, str]] = []
    for start in range(len(markers)):
        sequence: list[tuple[int, int, str]] = []
        expected = 1
        for marker in markers[start:]:
            if marker[1] == expected:
                sequence.append(marker)
                expected += 1
                if expected == 6:
                    best = sequence
            elif marker[1] == 1:
                sequence = [marker]
                expected = 2
            elif sequence:
                # Non-sequential marker; keep scanning from later candidates.
                continue
    return best


def fallback_combo_choices_from_tail(lines: list[str]) -> list[str] | None:
    tail = "\n".join(lines[-10:])
    marker = re.search(r"①\s*([^②③④⑤\n]+)\s*②\s*([^③④⑤\n]+)\s*③\s*([^④⑤\n]+)\s*④\s*([^⑤\n]+)\s*⑤\s*([^\n]+)", tail)
    if marker:
        return [normalize_choice_text(marker.group(i)) for i in range(1, 6)]
    return None


def split_question(raw_text: str) -> SplitResult:
    warnings: list[str] = []
    text = strip_tail_artifacts(normalize_common_ocr(normalize_whitespace(raw_text)))
    lines = text.split("\n")
    positions = find_choice_positions(lines)

    if len(positions) != 5:
        fallback = fallback_combo_choices_from_tail(lines)
        if fallback and len(fallback) == 5:
            warnings.append("used fallback tail choice parser")
            # Remove the final five circled choices from stem approximately.
            stem_text = re.sub(r"①.*$", "", text, flags=re.DOTALL).strip()
            return SplitResult(stem=join_wrapped_lines(stem_text.split("\n")), choices=fallback, warnings=warnings)
        warnings.append(f"could not find five sequential choices; found {len(positions)}")
        return SplitResult(stem=join_wrapped_lines(lines), choices=["", "", "", "", ""], warnings=warnings)

    first_choice_line = positions[0][0]
    stem = join_wrapped_lines(lines[:first_choice_line])
    choices: list[str] = []
    for seq_index, (line_index, number, rest) in enumerate(positions):
        if number != seq_index + 1:
            warnings.append(f"unexpected choice marker order at choice {seq_index + 1}: {number}")
        next_line = positions[seq_index + 1][0] if seq_index + 1 < len(positions) else len(lines)
        body_lines = [rest] + lines[line_index + 1 : next_line]
        choices.append(normalize_choice_text("\n".join(body_lines)))

    if any(not choice for choice in choices):
        warnings.append("one or more choices are empty after splitting")
    return SplitResult(stem=stem, choices=choices, warnings=warnings)


def merge_note(existing: str, addition: str) -> str:
    existing = (existing or "").strip()
    if not existing:
        return addition
    if addition in existing:
        return existing
    return existing + "\n" + addition


def preprocess_state(state: dict[str, Any], *, set_status: str | None) -> tuple[int, list[str]]:
    candidates = state.get("candidates")
    if not isinstance(candidates, list):
        raise SystemExit("Review state has no candidates list")

    changed = 0
    report: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("candidate_type") != "question":
            continue
        qno = candidate.get("question_number")
        raw_text = candidate.get("raw_ocr_text")
        if not isinstance(qno, int) or not isinstance(raw_text, str) or not raw_text.strip():
            continue

        result = split_question(raw_text)
        old_stem = candidate.get("stem")
        old_choices = candidate.get("choices")
        parse_failed = not result.stem.strip() or any(not choice for choice in result.choices)
        if parse_failed:
            note = "auto-preprocess skipped: parse failed"
            if result.warnings:
                note += "; " + " | ".join(result.warnings)
            candidate["notes"] = merge_note(str(candidate.get("notes") or ""), note)
            report.append(f"q{qno:02d}: skipped (parse failed, kept existing data)")
            continue

        candidate["stem"] = result.stem
        candidate["choices"] = result.choices
        candidate["manually_edited"] = True
        if set_status and candidate.get("status") == "unreviewed":
            candidate["status"] = set_status
        note = "auto-preprocessed from raw OCR; visual check required"
        if result.warnings:
            note += "; " + " | ".join(result.warnings)
        candidate["notes"] = merge_note(str(candidate.get("notes") or ""), note)

        if old_stem != result.stem or old_choices != result.choices:
            changed += 1
        report.append(f"q{qno:02d}: choices={sum(1 for c in result.choices if c)} warnings={result.warnings or '-'}")

    state["updated_at"] = datetime.now().isoformat()
    return changed, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-id", required=True, help="Exam id, e.g. '2021 추리논증'")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="Data root, default: data")
    parser.add_argument("--state-path", default=None, help="Override review state path")
    parser.add_argument(
        "--set-status",
        choices=["unreviewed", "needs_fix"],
        default=None,
        help="Optionally change unreviewed question candidates to this status after preprocessing.",
    )
    parser.add_argument("--no-backup", action="store_true", help="Do not create a timestamped backup")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and print report without writing")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    state_path = Path(args.state_path) if args.state_path else data_root / "verification" / args.exam_id / "crop-review-state.json"
    if not state_path.exists():
        raise SystemExit(f"Review state not found: {state_path}")

    state = read_json(state_path)
    changed, report = preprocess_state(state, set_status=args.set_status)

    print(f"State path: {state_path}")
    print(f"Changed question candidates: {changed}")
    for line in report:
        print(line)

    if args.dry_run:
        print("Dry run only; no files written.")
        return

    if not args.no_backup:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = state_path.with_name(f"{state_path.stem}.before-preprocess-{timestamp}{state_path.suffix}")
        shutil.copy2(state_path, backup_path)
        print(f"Backup written: {backup_path}")

    write_json(state_path, state)
    print("Review state updated. Open the verification workbench and visually check every preprocessed candidate before accepting.")


if __name__ == "__main__":
    main()
