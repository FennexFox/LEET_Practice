from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


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


def _ocr_args(**overrides):
    defaults = {
        "paddle_lang": "korean",
        "paddle_device": None,
        "paddle_cpu_threads": 4,
        "paddle_disable_mkldnn": True,
        "paddle_text_recognition_batch_size": 32,
        "paddle_disable_pir": True,
        "paddle_disable_doc_preprocess": True,
        "include_raw_paddle_payload": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _raw_block(module, index: int, page: int, column: str, tmp_path: Path):
    return module.RawBlock(
        sequence_index=index,
        page=page,
        column=column,
        page_image_path=str(tmp_path / f"page_{page:03d}.png"),
        image_path=str(tmp_path / f"page_{page:03d}_{column}.png"),
        page_bbox=[0, 0, 100, 200],
        local_size=[100, 200],
    )


def test_prepare_page_column_blocks_preserves_page_column_reading_order(tmp_path: Path, monkeypatch) -> None:
    module = _load_suggest_question_crops()
    render_calls: list[int] = []

    def fake_render(pdf_path, page, dpi, run_dir, args):
        render_calls.append(page)
        return tmp_path / f"page_{page:03d}.png"

    def fake_crop(page_image_path, run_dir, page, args):
        return [
            {
                "page": page,
                "column": "left",
                "page_image_path": str(page_image_path),
                "image_path": str(tmp_path / f"page_{page:03d}_left.png"),
                "page_bbox": [0, 0, 100, 200],
                "local_size": [100, 200],
            },
            {
                "page": page,
                "column": "right",
                "page_image_path": str(page_image_path),
                "image_path": str(tmp_path / f"page_{page:03d}_right.png"),
                "page_bbox": [100, 0, 200, 200],
                "local_size": [100, 200],
            },
        ]

    monkeypatch.setitem(module.prepare_page_column_blocks.__globals__, "render_pdf_page_cached", fake_render)
    monkeypatch.setitem(module.prepare_page_column_blocks.__globals__, "crop_page_columns", fake_crop)

    blocks = module.prepare_page_column_blocks(
        SimpleNamespace(pages="1-2", pdf=Path("paper.pdf"), dpi=300),
        tmp_path,
    )

    assert render_calls == [1, 2]
    assert [(block.sequence_index, block.page, block.column) for block in blocks] == [
        (0, 1, "left"),
        (1, 1, "right"),
        (2, 2, "left"),
        (3, 2, "right"),
    ]


def test_run_ocr_for_blocks_uses_batch_and_writes_compact_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_suggest_question_crops()
    raw_blocks = [_raw_block(module, 0, 1, "left", tmp_path), _raw_block(module, 1, 1, "right", tmp_path)]

    def fake_batch(image_paths, args):
        assert [path.name for path in image_paths] == ["page_001_left.png", "page_001_right.png"]
        return [
            ("", {"language": "korean", "runtime_flags": {}, "rows": [{"text": "1. left", "confidence": 0.9}]}),
            ("", {"language": "korean", "runtime_flags": {}, "rows": [{"text": "2. right", "confidence": 0.8}]}),
        ]

    monkeypatch.setitem(module.run_ocr_for_blocks.__globals__, "run_paddleocr_batch", fake_batch)

    ocr_blocks, errors, interrupted = module.run_ocr_for_blocks(raw_blocks, _ocr_args(), tmp_path)

    assert errors == []
    assert interrupted is False
    assert [block.raw_rows[0]["text"] for block in ocr_blocks] == ["1. left", "2. right"]
    assert sorted(path.name for path in tmp_path.glob("*.paddleocr.*")) == [
        "page_001_left.paddleocr.json",
        "page_001_left.paddleocr.txt",
        "page_001_right.paddleocr.json",
        "page_001_right.paddleocr.txt",
    ]
    payload = json.loads((tmp_path / "page_001_left.paddleocr.json").read_text(encoding="utf-8"))
    assert set(payload) == {
        "artifact_type",
        "verified",
        "status",
        "engine",
        "language",
        "runtime_flags",
        "page",
        "column",
        "image_path",
        "page_bbox",
        "local_size",
        "options",
        "rows",
    }


def test_run_ocr_for_blocks_falls_back_when_batch_fails(tmp_path: Path, monkeypatch) -> None:
    module = _load_suggest_question_crops()
    raw_blocks = [_raw_block(module, 0, 1, "left", tmp_path), _raw_block(module, 1, 1, "right", tmp_path)]
    calls: list[str] = []

    def fake_batch(image_paths, args):
        raise ValueError("shape mismatch")

    def fake_single(block, args, run_dir):
        calls.append(block["column"])
        return ([{"text": block["column"], "confidence": 1.0}], None)

    monkeypatch.setitem(module.run_ocr_for_blocks.__globals__, "run_paddleocr_batch", fake_batch)
    monkeypatch.setitem(module.run_ocr_for_blocks.__globals__, "run_ocr_for_block", fake_single)

    ocr_blocks, errors, interrupted = module.run_ocr_for_blocks(raw_blocks, _ocr_args(), tmp_path)

    assert errors == []
    assert interrupted is False
    assert calls == ["left", "right"]
    assert [block.raw_rows[0]["text"] for block in ocr_blocks] == ["left", "right"]


def test_run_ocr_for_blocks_falls_back_on_batch_result_count_mismatch(tmp_path: Path, monkeypatch) -> None:
    module = _load_suggest_question_crops()
    raw_blocks = [_raw_block(module, 0, 1, "left", tmp_path), _raw_block(module, 1, 1, "right", tmp_path)]
    calls: list[str] = []

    def fake_batch(image_paths, args):
        return [("", {"language": "korean", "runtime_flags": {}, "rows": []})]

    def fake_single(block, args, run_dir):
        calls.append(block["column"])
        return ([{"text": block["column"], "confidence": 1.0}], None)

    monkeypatch.setitem(module.run_ocr_for_blocks.__globals__, "run_paddleocr_batch", fake_batch)
    monkeypatch.setitem(module.run_ocr_for_blocks.__globals__, "run_ocr_for_block", fake_single)

    ocr_blocks, errors, interrupted = module.run_ocr_for_blocks(raw_blocks, _ocr_args(), tmp_path)

    assert errors == []
    assert interrupted is False
    assert calls == ["left", "right"]
    assert [block.raw_rows[0]["text"] for block in ocr_blocks] == ["left", "right"]


def test_build_stream_preserves_partial_ocr_blocks_after_keyboard_interrupt(tmp_path: Path, monkeypatch) -> None:
    module = _load_suggest_question_crops()
    raw_blocks = [_raw_block(module, 0, 1, "left", tmp_path), _raw_block(module, 1, 1, "right", tmp_path)]
    calls: list[str] = []

    def fake_prepare(args, run_dir):
        return raw_blocks

    def fake_single(block, args, run_dir):
        calls.append(block["column"])
        if block["column"] == "right":
            raise KeyboardInterrupt
        return ([{"text": "1. kept", "confidence": 1.0, "box": [1, 20, 20, 40]}], None)

    monkeypatch.setitem(module.build_stream.__globals__, "prepare_page_column_blocks", fake_prepare)
    monkeypatch.setitem(module.run_ocr_for_blocks.__globals__, "run_paddleocr_batch", lambda *_: (_ for _ in ()).throw(ValueError("no batch")))
    monkeypatch.setitem(module.run_ocr_for_blocks.__globals__, "run_ocr_for_block", fake_single)
    monkeypatch.setitem(module.build_suggestions_payload.__globals__, "save_candidate_crops", lambda **_: [])
    monkeypatch.setitem(module.build_suggestions_payload.__globals__, "save_annotated_blocks", lambda *_, **__: [])

    args = SimpleNamespace(
        pages="1",
        pdf=Path("paper.pdf"),
        dpi=300,
        content_padding=0,
        stream_gap=40,
        min_anchor_score=0.48,
        allow_weak_question_anchors=False,
        no_annotated_blocks=True,
        crop_top=0.05,
        crop_bottom=0.94,
        crop_left=0.05,
        crop_right=0.95,
        center_gutter=0.012,
        crop_padding=24,
        keep_crop_part_images=False,
        include_raw_paddle_payload=False,
        reuse_existing_images=False,
        paddle_lang="korean",
        paddle_device=None,
        paddle_cpu_threads=4,
        paddle_disable_mkldnn=True,
        paddle_text_recognition_batch_size=None,
        paddle_disable_pir=True,
        paddle_disable_doc_preprocess=True,
        paddle_preimport_torch=True,
        paddle_preimport_paddle=False,
    )

    payload = module.build_stream(args, tmp_path)

    assert calls == ["left", "right"]
    assert payload["status"] == "partial_interrupted"
    assert payload["interrupted"] is True
    assert [block["block_id"] for block in payload["blocks"]] == ["p001_left"]
    assert [row["text"] for row in payload["rows"]] == ["1. kept"]


def test_suggestions_payload_top_level_schema_is_stable(tmp_path: Path) -> None:
    module = _load_suggest_question_crops()
    args = SimpleNamespace(
        pages="1",
        pdf=Path("paper.pdf"),
        dpi=300,
        crop_top=0.05,
        crop_bottom=0.94,
        crop_left=0.05,
        crop_right=0.95,
        center_gutter=0.012,
        content_padding=18,
        crop_padding=24,
        keep_crop_part_images=False,
        stream_gap=40,
        min_anchor_score=0.48,
        allow_weak_question_anchors=False,
        include_raw_paddle_payload=False,
        reuse_existing_images=False,
        paddle_lang="korean",
        paddle_device=None,
        paddle_cpu_threads=4,
        paddle_disable_mkldnn=True,
        paddle_text_recognition_batch_size=None,
        paddle_disable_pir=True,
        paddle_disable_doc_preprocess=True,
        paddle_preimport_torch=True,
        paddle_preimport_paddle=False,
        no_annotated_blocks=True,
    )

    payload = module.build_suggestions_payload(
        args,
        tmp_path,
        [],
        [],
        [],
        [],
        interrupted=False,
    )

    assert list(payload) == [
        "artifact_type",
        "created_at",
        "verified",
        "source",
        "options",
        "model",
        "status",
        "interrupted",
        "processed_pages",
        "blocks",
        "rows",
        "set_header_candidates",
        "selected_set_headers",
        "anchor_candidates",
        "selected_anchors",
        "suggestions",
        "annotated_block_paths",
        "ocr_errors",
        "timings",
    ]
    assert set(payload["timings"]) == {
        "anchor_detection_seconds",
        "candidate_crops_seconds",
        "annotated_blocks_seconds",
        "build_suggestions_payload_seconds",
    }
