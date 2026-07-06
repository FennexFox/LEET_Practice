from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_preprocess_verification_state():
    tools_dir = Path(__file__).resolve().parents[1] / "tools"
    spec = importlib.util.spec_from_file_location(
        "preprocess_verification_state",
        tools_dir / "preprocess_verification_state.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preprocess_state_preserves_existing_question_data_when_parse_fails() -> None:
    module = _load_preprocess_verification_state()
    state = {
        "candidates": [
            {
                "candidate_type": "question",
                "question_number": 1,
                "raw_ocr_text": "Question text without usable choice markers",
                "stem": "Existing stem",
                "choices": ["A", "B", "C", "D", "E"],
                "status": "unreviewed",
                "notes": "existing note",
            }
        ]
    }

    changed, report = module.preprocess_state(state, set_status="needs_fix")
    candidate = state["candidates"][0]

    assert changed == 0
    assert candidate["stem"] == "Existing stem"
    assert candidate["choices"] == ["A", "B", "C", "D", "E"]
    assert candidate["status"] == "unreviewed"
    assert candidate.get("manually_edited") is None
    assert "auto-preprocess skipped: parse failed" in candidate["notes"]
    assert report == ["q01: skipped (parse failed, kept existing data)"]
