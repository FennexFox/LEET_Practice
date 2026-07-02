#!/usr/bin/env python3
"""Prefill verification workbench question fields from assistant JSONL drafts.

This is intentionally a staging helper. It updates crop-review-state.json, not
verified_questions.jsonl. The workbench remains the source of review decisions;
verified_questions.jsonl should be regenerated from accepted candidates only.

Example:
    python tools/prefill_assisted_question_drafts.py --exam-id "2022 추리논증" --dry-run
    python tools/prefill_assisted_question_drafts.py --exam-id "2022 추리논증"
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DATA_ROOT = Path("data")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def draft_question_no(row: dict[str, Any]) -> int:
    value = row.get("question_no")
    if not isinstance(value, int) or value <= 0:
        raise SystemExit(f"Draft row has invalid question_no: {value!r}")
    return value


def draft_choices(row: dict[str, Any]) -> list[str]:
    raw_choices = row.get("choices")
    if not isinstance(raw_choices, list) or len(raw_choices) != 5:
        raise SystemExit(f"Draft q{draft_question_no(row):03d} must have exactly five choices")
    choices: list[str] = []
    for index, choice in enumerate(raw_choices, start=1):
        if not isinstance(choice, dict):
            raise SystemExit(f"Draft q{draft_question_no(row):03d} choice {index} is not an object")
        text = choice.get("text")
        if not isinstance(text, str) or not text.strip():
            raise SystemExit(f"Draft q{draft_question_no(row):03d} choice {index} has empty text")
        choices.append(text.strip())
    return choices


def note_for(row: dict[str, Any]) -> str:
    flags = row.get("review_flags")
    if not flags:
        return "assistant draft imported; visual check required"
    if not isinstance(flags, list):
        return "assistant draft imported; visual check required"
    clean_flags = [str(flag).strip() for flag in flags if str(flag).strip()]
    return "assistant draft imported; " + " | ".join(clean_flags)


def merge_note(existing: str, addition: str) -> str:
    existing = (existing or "").strip()
    addition = addition.strip()
    if not existing:
        return addition
    if addition in existing:
        return existing
    return existing + "\n" + addition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-id", required=True, help="Exam id, e.g. '2022 추리논증'")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="Data root, default: data")
    parser.add_argument(
        "--draft-path",
        default=None,
        help="Assistant draft JSONL path. Defaults to data/verification/<exam-id>/assisted_questions_12_40.jsonl",
    )
    parser.add_argument(
        "--state-path",
        default=None,
        help="Review state path. Defaults to data/verification/<exam-id>/crop-review-state.json",
    )
    parser.add_argument(
        "--set-unreviewed-to-needs-fix",
        action="store_true",
        help="Change only unreviewed imported candidates to needs_fix so they are easy to filter in the workbench.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped backup before writing.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned updates without writing files")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    verification_dir = data_root / "verification" / args.exam_id
    draft_path = Path(args.draft_path) if args.draft_path else verification_dir / "assisted_questions_12_40.jsonl"
    state_path = Path(args.state_path) if args.state_path else verification_dir / "crop-review-state.json"

    if not draft_path.exists():
        raise SystemExit(f"Draft file not found: {draft_path}")
    if not state_path.exists():
        raise SystemExit(f"Review state not found: {state_path}")

    drafts = {draft_question_no(row): row for row in read_jsonl(draft_path)}
    state = read_json(state_path)
    candidates = state.get("candidates")
    if not isinstance(candidates, list):
        raise SystemExit(f"Review state has no candidates list: {state_path}")

    updated: list[int] = []
    missing: list[int] = []
    skipped_non_question: list[int] = []

    by_question_no: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        qno = candidate.get("question_number")
        if isinstance(qno, int):
            by_question_no[qno] = candidate

    for qno, draft in sorted(drafts.items()):
        candidate = by_question_no.get(qno)
        if candidate is None:
            missing.append(qno)
            continue
        if candidate.get("candidate_type") != "question":
            skipped_non_question.append(qno)
            continue

        stem = draft.get("stem")
        if not isinstance(stem, str) or not stem.strip():
            raise SystemExit(f"Draft q{qno:03d} has empty stem")

        candidate["stem"] = stem.strip()
        candidate["choices"] = draft_choices(draft)
        candidate["manually_edited"] = True
        candidate["notes"] = merge_note(str(candidate.get("notes") or ""), note_for(draft))

        if args.set_unreviewed_to_needs_fix and candidate.get("status") == "unreviewed":
            candidate["status"] = "needs_fix"

        updated.append(qno)

    state["updated_at"] = datetime.now().isoformat()

    print(f"Draft path: {draft_path}")
    print(f"State path: {state_path}")
    print(f"Updated candidates: {len(updated)} -> {updated}")
    if missing:
        print(f"Missing question candidates: {missing}")
    if skipped_non_question:
        print(f"Skipped non-question candidates: {skipped_non_question}")

    if args.dry_run:
        print("Dry run only; no files written.")
        return

    if not args.no_backup:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = state_path.with_name(f"{state_path.stem}.before-assisted-prefill-{timestamp}{state_path.suffix}")
        shutil.copy2(state_path, backup_path)
        print(f"Backup written: {backup_path}")

    write_json(state_path, state)
    print("Review state updated. Open the verification workbench and visually check imported candidates before accepting them.")


if __name__ == "__main__":
    main()
