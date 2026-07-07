#!/usr/bin/env python3
"""Rebuild verified draft JSONL files from crop-review-state.json.

This does not promote to canonical. It only rewrites
verified_passages.jsonl and verified_questions.jsonl from the current review
state, which is useful after scripted edits to crop-review-state.json.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from leet_practice.verification import build_verified_drafts, load_review_state, validate_promotion, write_verified_drafts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-id", required=True)
    parser.add_argument("--data-root", default="data")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    state = load_review_state(args.exam_id, data_root=data_root)
    drafts = build_verified_drafts(state)
    validate_promotion(*drafts)
    passage_path, question_path = write_verified_drafts(state, data_root=data_root, drafts=drafts)
    print(f"Rebuilt verified passage drafts: {passage_path}")
    print(f"Rebuilt verified question drafts: {question_path}")


if __name__ == "__main__":
    main()
