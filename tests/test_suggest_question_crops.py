from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_suggest_question_crops():
    tools_dir = Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(tools_dir))
    spec = importlib.util.spec_from_file_location("suggest_question_crops", tools_dir / "suggest_question_crops.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_standalone_choice_number_near_content_top_is_not_excluded() -> None:
    module = _load_suggest_question_crops()

    assert module.classify_excluded_row("2", [231, 745, 313, 797], 1537, 4415) == []


def test_standalone_page_number_at_top_edge_is_excluded() -> None:
    module = _load_suggest_question_crops()

    assert module.classify_excluded_row("2", [171, 158, 302, 314], 1537, 4415) == [
        "standalone-page-number-at-page-edge"
    ]


def test_edge_header_fragment_ocr_as_geuho_is_excluded() -> None:
    module = _load_suggest_question_crops()

    assert module.classify_excluded_row("\uadf8\ud638", [0, 595, 93, 681], 1392, 4415) == [
        "short-header-footer-fragment-at-page-edge"
    ]
