#!/usr/bin/env python3
"""Apply review overrides to a verification crop-review-state.json file.

The normal verified_questions.jsonl workflow remains separate; this script only
updates the workbench state fields consumed by that workflow.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

VALID_STATUSES = {"unreviewed", "needs_fix", "accepted", "rejected"}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clean_choices(raw: Any, qno: Any) -> list[str]:
    if not isinstance(raw, list) or len(raw) != 5:
        raise SystemExit(f"Override q{qno} must have exactly five choices")
    values: list[str] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
        else:
            text = ""
        if not text:
            raise SystemExit(f"Override q{qno} choice {index} is empty")
        values.append(text)
    return values


def choice_texts(row: dict[str, Any], patterns: dict[str, Any]) -> list[str] | None:
    if "choice_pattern" in row:
        key = str(row["choice_pattern"])
        if key not in patterns:
            raise SystemExit(f"Unknown choice_pattern for q{row.get('question_no')}: {key}")
        return _clean_choices(patterns[key], row.get("question_no"))
    if "choices" in row:
        return _clean_choices(row["choices"], row.get("question_no"))
    return None


def merge_note(existing: str, addition: str) -> str:
    existing = (existing or "").strip()
    addition = addition.strip()
    if not addition:
        return existing
    if not existing:
        return addition
    if addition in existing:
        return existing
    return existing + "\n" + addition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-id", required=True)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--state-path", default=None)
    parser.add_argument("--overrides", default=None)
    parser.add_argument(
        "--include-accepted",
        action="store_true",
        help="Also update already accepted candidates. Default: skip them.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    verification_dir = data_root / "verification" / args.exam_id
    state_path = Path(args.state_path) if args.state_path else verification_dir / "crop-review-state.json"
    overrides_path = Path(args.overrides) if args.overrides else verification_dir / "review-overrides.json"

    state = read_json(state_path)
    overrides = read_json(overrides_path)
    rows = overrides.get("candidates")
    patterns = overrides.get("choice_patterns", {})
    if not isinstance(rows, list):
        raise SystemExit(f"Overrides must contain candidates list: {overrides_path}")
    if not isinstance(patterns, dict):
        raise SystemExit("choice_patterns must be an object when provided")

    candidates = state.get("candidates")
    if not isinstance(candidates, list):
        raise SystemExit(f"State has no candidates list: {state_path}")

    by_id = {candidate.get("candidate_id"): candidate for candidate in candidates if isinstance(candidate, dict)}
    by_qno = {candidate.get("question_number"): candidate for candidate in candidates if isinstance(candidate, dict)}
    updated: list[str] = []
    skipped_accepted: list[str] = []

    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("Override candidate row must be an object")
        candidate = by_id.get(row.get("candidate_id")) or by_qno.get(row.get("question_no"))
        if not candidate:
            raise SystemExit(f"No matching candidate for override row: {row}")
        if candidate.get("candidate_type") != "question":
            raise SystemExit(f"Override target is not a question candidate: {candidate.get('candidate_id')}")

        candidate_id = str(candidate.get("candidate_id"))
        row_question_no = row.get("question_no")
        question_number_changed = False
        if isinstance(row_question_no, int) and candidate.get("question_number") != row_question_no:
            candidate["question_number"] = row_question_no
            candidate["manually_edited"] = True
            question_number_changed = True

        if candidate.get("status") == "accepted" and not args.include_accepted:
            answer_changed = False
            if "correct_answer" in row:
                answer = row["correct_answer"]
                if not isinstance(answer, int) or not 1 <= answer <= 5:
                    raise SystemExit(f"Invalid correct_answer for q{row.get('question_no')}: {answer!r}")
                if candidate.get("correct_answer") != answer:
                    candidate["correct_answer"] = answer
                    candidate["manually_edited"] = True
                    answer_changed = True
            if question_number_changed or answer_changed:
                updated.append(candidate_id)
            else:
                skipped_accepted.append(candidate_id)
            continue

        if "status" in row:
            status = row["status"]
            if status not in VALID_STATUSES:
                raise SystemExit(f"Invalid status for q{row.get('question_no')}: {status!r}")
            candidate["status"] = status
        if "correct_answer" in row:
            answer = row["correct_answer"]
            if not isinstance(answer, int) or not 1 <= answer <= 5:
                raise SystemExit(f"Invalid correct_answer for q{row.get('question_no')}: {answer!r}")
            candidate["correct_answer"] = answer
        if "stem" in row:
            stem = str(row["stem"]).strip()
            if not stem:
                raise SystemExit(f"Empty stem for q{row.get('question_no')}")
            candidate["stem"] = stem
        choices = choice_texts(row, patterns)
        if choices is not None:
            candidate["choices"] = choices

        flags = row.get("review_flags") or []
        if isinstance(flags, list) and flags:
            flag_text = " | ".join(str(flag).strip() for flag in flags if str(flag).strip())
            note = "verified override applied; " + flag_text
        else:
            note = "verified override applied; source checked against regenerated crop candidate/raw PDF where available"
        candidate["notes"] = merge_note(str(candidate.get("notes") or ""), note)
        candidate["manually_edited"] = True
        updated.append(candidate_id)

    state["updated_at"] = datetime.now().isoformat()
    print(f"State: {state_path}")
    print(f"Overrides: {overrides_path}")
    print(f"Updated {len(updated)} candidates: {', '.join(updated)}")

    if args.dry_run:
        print("Dry run only; no files written.")
        return
    if not args.no_backup:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = state_path.with_name(f"{state_path.stem}.before-review-overrides-{timestamp}{state_path.suffix}")
        shutil.copy2(state_path, backup_path)
        print(f"Backup written: {backup_path}")
    write_json(state_path, state)
    print("Review state updated.")


if __name__ == "__main__":
    main()
