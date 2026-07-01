#!/usr/bin/env python
"""Suggest candidate LEET question crops from PaddleOCR page-column streams.

The output is a candidate-generation artifact for human review. It does not
write verified question text and it does not write into canonical review data.

Example:
    uv run python tools/suggest_question_crops.py \
        --pdf "data/raw_pdfs/leet-2026-verbal-even.pdf" \
        --pages 1-10 \
        --paddle-device gpu:0 \
        --paddle-preimport-paddle
"""

from __future__ import annotations

import argparse
import json
import re
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from leet_practice.compare_ocr_engines import (
    extract_paddle_rows,
    render_pdf_page,
    run_paddleocr,
    run_paddleocr_batch,
    safe_jsonable,
)


COLUMN_ORDER = ("left", "right")
QUESTION_RE = re.compile(r"^\s*(?:\uBB38\s*)?([1-9]|[1-3]\d|40)\s*(?:(?P<mark>[.)\uFF0E\uFF09])|(?P<space>\s+))")
SET_HEADER_RE = re.compile(
    r"^\s*[\[\(\u3010\u3014\uFF3B]\s*([1-9]|[1-3]\d|40)\s*(?:~|-|\u301C|\uFF5E|\u2013|\u2014)\s*([1-9]|[1-3]\d|40)\s*[\]\)\u3011\u3015\uFF3D]"
)
LIKELY_CHOICE_OR_INLINE_RE = re.compile(
    r"^\s*(?:[1-9]|[1-3]\d|40)\s*(?:\[[A-Ea-e]\]|[A-Ea-e]\]|[\u2460-\u2464]|[?\uFF1F]+[\u2460-\u2464])"
)
LIKELY_QUANTITY_RE = re.compile(
    r"^\s*(?:[1-9]|[1-3]\d|40)\s*(?:\uB144|\uAC1C|\uBA85|\uCABD|\uC810|%|\u339D|cm|mm|m|kg)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"^\s*(?:19|20)\d{2}\b")
HEADER_FOOTER_RE = re.compile(
    r"(\uBC95\uD559\uC801\uC131\uC2DC\uD5D8|\uC5B8\uC5B4\uC774\uD574|\uCD94\uB9AC\uB17C\uC99D|"
    r"\uB17C\uC220|\uD640\uC218\uD615|\uC9DD\uC218\uD615|\uC131\uBA85|\uC218\uD5D8\uBC88\uD638|\uAD50\uC2DC)"
)
HEADER_FOOTER_EDGE_TEXT_RE = re.compile(
    r"^(?:"
    r"\uC5B8\uC5B4|\uC774\uD574|\uC5B8\d+|"
    r"\uCD94\uB9AC|\uB17C\uC99D|\uB17C\uC220|"
    r"\uD640\uC218\uD615|\uC9DD\uC218\uD615|"
    r"\uC131\uBA85|\uC218\uD5D8|\uBC88\uD638|\uC218\uD5D8\uBC88\uD638|\uAD50\uC2DC|"
    r"\d+\s*\uD638|\uADF8\uD638"
    r")$"
)
HEADER_FOOTER_TOP_EDGE_RATIO = 0.18
HEADER_FOOTER_BOTTOM_EDGE_RATIO = 0.92
STANDALONE_NUMBER_TOP_EDGE_RATIO = 0.10


@dataclass(frozen=True)
class RawBlock:
    sequence_index: int
    page: int
    column: str
    page_image_path: str
    image_path: str
    page_bbox: list[int]
    local_size: list[int]

    def ocr_input(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "column": self.column,
            "page_image_path": self.page_image_path,
            "image_path": self.image_path,
            "page_bbox": self.page_bbox,
            "local_size": self.local_size,
        }


@dataclass(frozen=True)
class OcrBlock:
    raw_block: RawBlock
    raw_rows: list[dict[str, Any]]
    error: str | None = None


@dataclass(frozen=True)
class ColumnBlock:
    block_id: str
    page: int
    column: str
    page_image_path: str
    image_path: str
    page_bbox: list[int]
    local_size: list[int]
    content_bbox: list[int]
    content_page_bbox: list[int]
    stream_y_start: float
    stream_y_end: float


@dataclass(frozen=True)
class StreamRow:
    row_id: str
    block_id: str
    page: int
    column: str
    source_image_path: str
    local_bbox: list[int] | None
    source_page_bbox: list[int] | None
    content_block_bbox: list[int]
    stream_y_start: float
    stream_y_end: float
    text: str
    confidence: float | None
    excluded: bool
    exclusion_reasons: list[str]


@dataclass(frozen=True)
class AnchorCandidate:
    anchor_id: str
    question_number: int
    row_id: str
    block_id: str
    page: int
    column: str
    stream_y_start: float
    text: str
    confidence: float | None
    local_bbox: list[int] | None
    score: float
    reasons: list[str]
    selected: bool = False


@dataclass(frozen=True)
class SetHeaderAnchor:
    anchor_id: str
    start_question: int
    end_question: int
    row_id: str
    block_id: str
    page: int
    column: str
    stream_y_start: float
    text: str
    confidence: float | None
    local_bbox: list[int] | None
    score: float
    reasons: list[str]
    selected: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Suggest candidate LEET question crops from a PaddleOCR virtual reading stream."
    )
    parser.add_argument("--pdf", type=Path, required=True, help="Input PDF path.")
    parser.add_argument(
        "--pages",
        required=True,
        help="1-based page range, for example '1-10' or '1,3,5-7'.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI. Default: 300.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/question_crop_suggestions"),
        help="Directory where candidate suggestions are written.",
    )
    parser.add_argument("--run-id", default=None, help="Optional output run directory name.")

    parser.add_argument("--crop-top", type=float, default=0.05, help="Top crop ratio for columns.")
    parser.add_argument("--crop-bottom", type=float, default=0.94, help="Bottom crop ratio for columns.")
    parser.add_argument("--crop-left", type=float, default=0.05, help="Left crop ratio for columns.")
    parser.add_argument("--crop-right", type=float, default=0.95, help="Right crop ratio for columns.")
    parser.add_argument(
        "--center-gutter",
        type=float,
        default=0.012,
        help="Ratio removed around the center fold when splitting columns.",
    )
    parser.add_argument(
        "--content-padding",
        type=int,
        default=18,
        help="Pixel padding around OCR row unions when estimating content blocks. Default: 18.",
    )
    parser.add_argument(
        "--crop-padding",
        type=int,
        default=24,
        help="Pixel padding around emitted candidate crop parts. Default: 24.",
    )
    parser.add_argument(
        "--keep-crop-part-images",
        action="store_true",
        help="Keep per-candidate part PNGs after preview images are stitched. Default: false.",
    )
    parser.add_argument(
        "--stream-gap",
        type=int,
        default=40,
        help="Virtual vertical gap inserted between page-column blocks. Default: 40.",
    )
    parser.add_argument(
        "--min-anchor-score",
        type=float,
        default=0.48,
        help="Minimum conservative anchor score. Default: 0.48.",
    )
    parser.add_argument(
        "--allow-weak-question-anchors",
        action="store_true",
        help="Allow bare number+space question anchors. Default: false; punctuation anchors are preferred.",
    )
    parser.add_argument(
        "--include-raw-paddle-payload",
        action="store_true",
        help="Debug only: include the full raw PaddleOCR payload in per-block JSON. Default: false.",
    )
    parser.add_argument(
        "--reuse-existing-images",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Reuse rendered page and column PNGs already present in the run directory. Default: false.",
    )
    parser.add_argument(
        "--no-annotated-blocks",
        action="store_true",
        help="Skip annotated page-column block images.",
    )

    parser.add_argument(
        "--paddle-lang",
        default="korean",
        help="PaddleOCR language code. Try 'korean' first; if it fails, try 'ko'.",
    )
    parser.add_argument(
        "--paddle-device",
        default=None,
        help="Optional PaddleOCR device string, for example 'cpu' or 'gpu:0'.",
    )
    parser.add_argument(
        "--paddle-cpu-threads",
        type=int,
        default=4,
        help="CPU thread count passed to PaddleOCR when the installed version supports it.",
    )
    parser.add_argument(
        "--paddle-text-recognition-batch-size",
        type=int,
        default=None,
        help="Text recognition batch size passed to PaddleOCR when the installed version supports it.",
    )
    parser.add_argument(
        "--paddle-disable-mkldnn",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disable Paddle oneDNN/MKLDNN paths before importing PaddleOCR. Default: true.",
    )
    parser.add_argument(
        "--paddle-disable-pir",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disable Paddle PIR API before importing PaddleOCR. Default: true.",
    )
    parser.add_argument(
        "--paddle-disable-doc-preprocess",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disable PaddleOCR document orientation/unwarping/textline orientation models when supported. Default: true.",
    )
    parser.add_argument(
        "--paddle-preimport-torch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Import torch before PaddleOCR to avoid Windows DLL load-order conflicts. Default: true.",
    )
    parser.add_argument(
        "--paddle-preimport-paddle",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Import paddle before PaddleOCR. Useful for Paddle GPU builds on Windows. Default: false.",
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def make_run_dir(base_dir: Path, run_id: str | None) -> Path:
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def parse_pages(value: str) -> list[int]:
    pages: set[int] = set()
    for part in value.split(","):
        page_part = part.strip()
        if not page_part:
            continue
        if "-" in page_part:
            start_text, end_text = page_part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"Invalid page range: {page_part}")
            pages.update(range(start, end + 1))
        else:
            page = int(page_part)
            if page <= 0:
                raise ValueError(f"Invalid page number: {page_part}")
            pages.add(page)
    if not pages:
        raise ValueError("--pages did not contain any page numbers.")
    return sorted(pages)


def expected_page_image_path(run_dir: Path, page: int, dpi: int) -> Path:
    return run_dir / f"page_{page:03d}_{dpi}dpi.png"


def reusable_image(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def render_pdf_page_cached(pdf_path: Path, page: int, dpi: int, run_dir: Path, args: argparse.Namespace) -> Path:
    out_path = expected_page_image_path(run_dir, page, dpi)
    if args.reuse_existing_images and reusable_image(out_path):
        print(f"Reusing rendered page {page}: {out_path}")
        return out_path
    return render_pdf_page(pdf_path, page, dpi, run_dir)


def crop_page_columns(
    page_image_path: Path,
    run_dir: Path,
    page: int,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required. Run: uv sync --extra pdf") from exc

    with Image.open(page_image_path) as img:
        width, height = img.size
        top = int(height * args.crop_top)
        bottom = int(height * args.crop_bottom)
        left_margin = int(width * args.crop_left)
        right_margin = int(width * args.crop_right)
        mid = int(width * 0.5)
        gutter_px = int(width * args.center_gutter)

        if not (0 <= left_margin < mid - gutter_px < mid + gutter_px < right_margin <= width):
            raise ValueError("Invalid crop ratios. Check crop margins and center gutter.")
        if not (0 <= top < bottom <= height):
            raise ValueError("Invalid vertical crop ratios.")

        boxes = {
            "left": [left_margin, top, mid - gutter_px, bottom],
            "right": [mid + gutter_px, top, right_margin, bottom],
        }

        blocks: list[dict[str, Any]] = []
        for column in COLUMN_ORDER:
            bbox = boxes[column]
            out_path = run_dir / f"page_{page:03d}_{column}.png"
            if args.reuse_existing_images and reusable_image(out_path):
                print(f"Reusing page {page} {column} column: {out_path}")
            else:
                crop = img.crop(tuple(bbox))
                crop.save(out_path)
            blocks.append(
                {
                    "page": page,
                    "column": column,
                    "page_image_path": str(page_image_path),
                    "image_path": str(out_path),
                    "page_bbox": bbox,
                    "local_size": [bbox[2] - bbox[0], bbox[3] - bbox[1]],
                }
            )
    return blocks


def bbox_from_box(box: Any) -> list[int] | None:
    box = safe_jsonable(box)
    if box is None:
        return None
    points: list[tuple[float, float]] = []
    if isinstance(box, list):
        if len(box) == 4 and all(isinstance(v, int | float) for v in box):
            x0, y0, x1, y1 = box
            return [int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))]
        for item in box:
            if isinstance(item, list | tuple) and len(item) >= 2:
                x, y = item[0], item[1]
                if isinstance(x, int | float) and isinstance(y, int | float):
                    points.append((float(x), float(y)))
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [
        int(round(min(xs))),
        int(round(min(ys))),
        int(round(max(xs))),
        int(round(max(ys))),
    ]


def clamp_bbox(bbox: list[int], width: int, height: int) -> list[int]:
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(width, x0))
    y0 = max(0, min(height, y0))
    x1 = max(0, min(width, x1))
    y1 = max(0, min(height, y1))
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return [x0, y0, x1, y1]


def pad_bbox(bbox: list[int], padding: int, width: int, height: int) -> list[int]:
    return clamp_bbox(
        [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding],
        width,
        height,
    )


def union_bboxes(bboxes: list[list[int]]) -> list[int] | None:
    if not bboxes:
        return None
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]


def source_page_bbox(local_bbox: list[int] | None, page_bbox: list[int]) -> list[int] | None:
    if local_bbox is None:
        return None
    return [
        page_bbox[0] + local_bbox[0],
        page_bbox[1] + local_bbox[1],
        page_bbox[0] + local_bbox[2],
        page_bbox[1] + local_bbox[3],
    ]


def compact_ocr_rows(raw_rows: list[dict[str, Any]], block: dict[str, Any]) -> list[dict[str, Any]]:
    width, height = block["local_size"]
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        local_bbox = bbox_from_box(row.get("box"))
        if local_bbox is not None:
            local_bbox = clamp_bbox(local_bbox, width, height)
        confidence = row.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        rows.append(
            {
                "row_index": index,
                "text": str(row.get("text", "")).strip(),
                "confidence": confidence_value,
                "local_bbox": local_bbox,
                "source_page_bbox": source_page_bbox(local_bbox, block["page_bbox"]),
                "page": block["page"],
                "column": block["column"],
            }
        )
    return rows


def format_compact_ocr_text(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        confidence = row.get("confidence")
        text = str(row.get("text", ""))
        if isinstance(confidence, int | float):
            lines.append(f"{confidence:.3f}\t{text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def write_ocr_block_artifacts(
    block: dict[str, Any],
    payload: dict[str, Any],
    args: argparse.Namespace,
    run_dir: Path,
) -> list[dict[str, Any]]:
    label = f"page_{block['page']:03d}_{block['column']}"
    raw_rows = list(payload.get("rows") or extract_paddle_rows(payload))
    compact_rows = compact_ocr_rows(raw_rows, block)
    text_path = run_dir / f"{label}.paddleocr.txt"
    json_path = run_dir / f"{label}.paddleocr.json"
    text_path.write_text(format_compact_ocr_text(compact_rows), encoding="utf-8")

    compact_payload: dict[str, Any] = {
        "artifact_type": "candidate_question_crop_ocr_source",
        "verified": False,
        "status": "ok",
        "engine": "paddleocr",
        "language": payload.get("language"),
        "runtime_flags": payload.get("runtime_flags", {}),
        "page": block["page"],
        "column": block["column"],
        "image_path": block["image_path"],
        "page_bbox": block["page_bbox"],
        "local_size": block["local_size"],
        "options": {
            "paddle_lang": args.paddle_lang,
            "paddle_device": args.paddle_device,
            "paddle_cpu_threads": args.paddle_cpu_threads,
            "paddle_disable_mkldnn": args.paddle_disable_mkldnn,
            "paddle_text_recognition_batch_size": args.paddle_text_recognition_batch_size,
            "paddle_disable_pir": args.paddle_disable_pir,
            "paddle_disable_doc_preprocess": args.paddle_disable_doc_preprocess,
            "include_raw_paddle_payload": args.include_raw_paddle_payload,
        },
        "rows": compact_rows,
    }
    if args.include_raw_paddle_payload:
        compact_payload["raw"] = payload.get("raw")

    json_path.write_text(json.dumps(compact_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw_rows


def run_ocr_for_block(block: dict[str, Any], args: argparse.Namespace, run_dir: Path) -> tuple[list[dict[str, Any]], str | None]:
    label = f"page_{block['page']:03d}_{block['column']}"
    try:
        _, payload = run_paddleocr(Path(block["image_path"]), args)
        raw_rows = write_ocr_block_artifacts(block, payload, args, run_dir)
        return raw_rows, None
    except Exception as exc:  # noqa: BLE001 - one bad block should not suppress suggestions.json.
        error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        error_path = run_dir / f"{label}.paddleocr.error.txt"
        error_path.write_text(error_text, encoding="utf-8")
        return [], str(exc)


def classify_excluded_row(text: str, local_bbox: list[int] | None, width: int, height: int) -> list[str]:
    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped:
        return ["empty-ocr-row"]

    reasons: list[str] = []
    near_top = False
    near_bottom = False
    if local_bbox is not None:
        near_top = local_bbox[1] <= int(height * HEADER_FOOTER_TOP_EDGE_RATIO)
        near_bottom = local_bbox[3] >= int(height * HEADER_FOOTER_BOTTOM_EDGE_RATIO)

    standalone_number_near_top = False
    if local_bbox is not None:
        standalone_number_near_top = local_bbox[1] <= int(height * STANDALONE_NUMBER_TOP_EDGE_RATIO)

    if re.fullmatch(r"\d{1,3}", stripped) and (standalone_number_near_top or near_bottom):
        reasons.append("standalone-page-number-at-page-edge")

    if (near_top or near_bottom) and HEADER_FOOTER_RE.search(stripped):
        reasons.append("known-header-footer-fragment-at-page-edge")

    if (near_top or near_bottom) and HEADER_FOOTER_EDGE_TEXT_RE.fullmatch(stripped):
        reasons.append("short-header-footer-fragment-at-page-edge")

    if (
        (near_top or near_bottom)
        and not re.fullmatch(r"\d{1,3}", stripped)
        and re.fullmatch(r"[-\u2013\u2014\s\d]+", stripped)
    ):
        reasons.append("edge-rule-or-page-marker")

    return reasons


def make_block_and_rows(
    raw_block: dict[str, Any],
    raw_rows: list[dict[str, Any]],
    stream_y: float,
    args: argparse.Namespace,
) -> tuple[ColumnBlock, list[StreamRow]]:
    width, height = raw_block["local_size"]
    row_items: list[tuple[dict[str, Any], list[int] | None, list[str]]] = []
    for row in raw_rows:
        local_bbox = bbox_from_box(row.get("box"))
        if local_bbox is not None:
            local_bbox = clamp_bbox(local_bbox, width, height)
            if local_bbox[2] == local_bbox[0] or local_bbox[3] == local_bbox[1]:
                local_bbox = None
        exclusion_reasons = classify_excluded_row(str(row.get("text", "")), local_bbox, width, height)
        row_items.append((row, local_bbox, exclusion_reasons))

    content_union = union_bboxes([bbox for _, bbox, reasons in row_items if bbox is not None and not reasons])
    if content_union is None:
        content_bbox = [0, 0, width, height]
    else:
        content_bbox = pad_bbox(content_union, args.content_padding, width, height)

    content_height = max(1, content_bbox[3] - content_bbox[1])
    block_id = f"p{raw_block['page']:03d}_{raw_block['column']}"
    block = ColumnBlock(
        block_id=block_id,
        page=int(raw_block["page"]),
        column=str(raw_block["column"]),
        page_image_path=str(raw_block["page_image_path"]),
        image_path=str(raw_block["image_path"]),
        page_bbox=list(raw_block["page_bbox"]),
        local_size=[width, height],
        content_bbox=content_bbox,
        content_page_bbox=source_page_bbox(content_bbox, raw_block["page_bbox"]) or list(raw_block["page_bbox"]),
        stream_y_start=stream_y,
        stream_y_end=stream_y + content_height,
    )

    sortable_rows = sorted(
        enumerate(row_items),
        key=lambda item: (
            item[1][1][1] if item[1][1] is not None else 10**9,
            item[1][1][0] if item[1][1] is not None else item[0],
            item[0],
        ),
    )

    stream_rows: list[StreamRow] = []
    fallback_step = content_height / max(1, len(sortable_rows))
    for sorted_index, (original_index, (row, local_bbox, exclusion_reasons)) in enumerate(sortable_rows):
        if local_bbox is None:
            row_start = stream_y + (sorted_index * fallback_step)
            row_end = min(stream_y + content_height, row_start + fallback_step)
        else:
            row_start = stream_y + max(0, local_bbox[1] - content_bbox[1])
            row_end = stream_y + max(0, local_bbox[3] - content_bbox[1])
        confidence = row.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        stream_rows.append(
            StreamRow(
                row_id=f"{block_id}_r{original_index:03d}",
                block_id=block_id,
                page=block.page,
                column=block.column,
                source_image_path=block.image_path,
                local_bbox=local_bbox,
                source_page_bbox=source_page_bbox(local_bbox, block.page_bbox),
                content_block_bbox=content_bbox,
                stream_y_start=row_start,
                stream_y_end=max(row_start + 1, row_end),
                text=str(row.get("text", "")).strip(),
                confidence=confidence_value,
                excluded=bool(exclusion_reasons),
                exclusion_reasons=exclusion_reasons,
            )
        )

    return block, stream_rows


def left_edge_score(row: StreamRow, block: ColumnBlock, reasons: list[str]) -> float:
    if row.local_bbox is None:
        reasons.append("row-bbox-missing")
        return 0.35

    content_left = block.content_bbox[0]
    content_width = max(1, block.content_bbox[2] - block.content_bbox[0])
    left_distance = max(0, row.local_bbox[0] - content_left)
    left_slop = max(50, int(content_width * 0.16))
    reasons.append(f"left-edge-distance-px={left_distance}")
    return max(0.0, 1.0 - (left_distance / left_slop))


def confidence_score(row: StreamRow, reasons: list[str]) -> float:
    if row.confidence is None:
        reasons.append("ocr-confidence-missing")
        return 0.55
    score = max(0.0, min(1.0, row.confidence))
    reasons.append(f"ocr-confidence={score:.3f}")
    return score


def rejected_anchor_candidate(row: StreamRow, question_number: int, reasons: list[str]) -> AnchorCandidate:
    return AnchorCandidate(
        anchor_id=f"q{question_number:02d}_{row.row_id}",
        question_number=question_number,
        row_id=row.row_id,
        block_id=row.block_id,
        page=row.page,
        column=row.column,
        stream_y_start=row.stream_y_start,
        text=row.text,
        confidence=row.confidence,
        local_bbox=row.local_bbox,
        score=0.0,
        reasons=reasons,
    )


def score_anchor(row: StreamRow, block: ColumnBlock, allow_weak: bool) -> AnchorCandidate | None:
    if row.excluded:
        return None
    match = QUESTION_RE.match(row.text)
    if match is None:
        return None
    question_number = int(match.group(1))
    reasons: list[str] = ["question-number-at-line-start"]

    if YEAR_RE.match(row.text):
        reasons.append("rejected-year-like-number")
        return rejected_anchor_candidate(row, question_number, reasons)
    if LIKELY_CHOICE_OR_INLINE_RE.match(row.text):
        reasons.append("rejected-choice-or-inline-number-pattern")
        return rejected_anchor_candidate(row, question_number, reasons)
    if LIKELY_QUANTITY_RE.match(row.text):
        reasons.append("rejected-quantity-pattern")
        return rejected_anchor_candidate(row, question_number, reasons)

    confidence_component = confidence_score(row, reasons)
    left_component = left_edge_score(row, block, reasons)
    has_question_mark = bool(match.group("mark"))
    punctuation_score = 1.0 if has_question_mark else 0.10
    if match.group("mark"):
        reasons.append("number-has-question-punctuation")
    else:
        reasons.append("bare-number-space-penalized")
        if not allow_weak:
            reasons.append("rejected-weak-anchor-disabled")
            return rejected_anchor_candidate(row, question_number, reasons)

    score = (left_component * 0.52) + (confidence_component * 0.24) + (punctuation_score * 0.24)
    return AnchorCandidate(
        anchor_id=f"q{question_number:02d}_{row.row_id}",
        question_number=question_number,
        row_id=row.row_id,
        block_id=row.block_id,
        page=row.page,
        column=row.column,
        stream_y_start=row.stream_y_start,
        text=row.text,
        confidence=row.confidence,
        local_bbox=row.local_bbox,
        score=round(score, 4),
        reasons=reasons,
    )


def detect_anchor_candidates(
    rows: list[StreamRow],
    blocks_by_id: dict[str, ColumnBlock],
    min_score: float,
    allow_weak: bool,
) -> tuple[list[AnchorCandidate], list[AnchorCandidate]]:
    candidates: list[AnchorCandidate] = []
    for row in rows:
        candidate = score_anchor(row, blocks_by_id[row.block_id], allow_weak)
        if candidate is not None:
            candidates.append(candidate)

    selected: list[AnchorCandidate] = []
    last_question_number: int | None = None
    for candidate in sorted(candidates, key=lambda item: (item.stream_y_start, item.question_number)):
        if candidate.score < min_score:
            continue
        if last_question_number is not None and candidate.question_number <= last_question_number:
            continue
        reasons = list(candidate.reasons)
        if last_question_number is None:
            reasons.append("first-selected-anchor-in-page-range")
        elif candidate.question_number == last_question_number + 1:
            reasons.append("sequential-question-number")
        else:
            reasons.append(f"question-number-gap-from-{last_question_number}")
        selected_candidate = AnchorCandidate(
            **{
                **asdict(candidate),
                "selected": True,
                "reasons": reasons,
            }
        )
        selected.append(selected_candidate)
        last_question_number = candidate.question_number

    selected_ids = {candidate.anchor_id for candidate in selected}
    all_candidates = [
        AnchorCandidate(
            **{
                **asdict(candidate),
                "selected": candidate.anchor_id in selected_ids,
            }
        )
        for candidate in candidates
    ]
    return all_candidates, selected


def score_set_header(row: StreamRow, block: ColumnBlock) -> SetHeaderAnchor | None:
    if row.excluded:
        return None
    match = SET_HEADER_RE.match(row.text)
    if match is None:
        return None

    start_question = int(match.group(1))
    end_question = int(match.group(2))
    reasons = ["set-header-range-at-line-start"]
    if end_question < start_question:
        reasons.append("rejected-descending-range")
        score = 0.0
    elif end_question == start_question:
        reasons.append("rejected-single-question-range")
        score = 0.0
    else:
        left_component = left_edge_score(row, block, reasons)
        confidence_component = confidence_score(row, reasons)
        span = end_question - start_question + 1
        span_component = 1.0 if 2 <= span <= 6 else 0.55
        if span_component == 1.0:
            reasons.append(f"plausible-set-span={span}")
        else:
            reasons.append(f"unusual-set-span={span}")
        score = (left_component * 0.45) + (confidence_component * 0.25) + (span_component * 0.30)

    return SetHeaderAnchor(
        anchor_id=f"set_{start_question:02d}_{end_question:02d}_{row.row_id}",
        start_question=start_question,
        end_question=end_question,
        row_id=row.row_id,
        block_id=row.block_id,
        page=row.page,
        column=row.column,
        stream_y_start=row.stream_y_start,
        text=row.text,
        confidence=row.confidence,
        local_bbox=row.local_bbox,
        score=round(score, 4),
        reasons=reasons,
    )


def detect_set_header_candidates(
    rows: list[StreamRow],
    blocks_by_id: dict[str, ColumnBlock],
    min_score: float,
) -> tuple[list[SetHeaderAnchor], list[SetHeaderAnchor]]:
    candidates: list[SetHeaderAnchor] = []
    for row in rows:
        candidate = score_set_header(row, blocks_by_id[row.block_id])
        if candidate is not None:
            candidates.append(candidate)

    selected: list[SetHeaderAnchor] = []
    last_end_question = 0
    for candidate in sorted(candidates, key=lambda item: (item.stream_y_start, item.start_question, item.end_question)):
        if candidate.score < min_score:
            continue
        if candidate.start_question <= last_end_question:
            continue
        reasons = list(candidate.reasons)
        if not selected:
            reasons.append("first-selected-set-header-in-page-range")
        elif candidate.start_question == last_end_question + 1:
            reasons.append("sequential-set-header")
        else:
            reasons.append(f"set-question-gap-from-{last_end_question}")
        selected_candidate = SetHeaderAnchor(
            **{
                **asdict(candidate),
                "selected": True,
                "reasons": reasons,
            }
        )
        selected.append(selected_candidate)
        last_end_question = candidate.end_question

    selected_ids = {candidate.anchor_id for candidate in selected}
    all_candidates = [
        SetHeaderAnchor(
            **{
                **asdict(candidate),
                "selected": candidate.anchor_id in selected_ids,
            }
        )
        for candidate in candidates
    ]
    return all_candidates, selected


def intersect_interval(a0: float, a1: float, b0: float, b1: float) -> tuple[float, float] | None:
    start = max(a0, b0)
    end = min(a1, b1)
    if end <= start:
        return None
    return start, end


def rows_in_interval(rows: list[StreamRow], interval_start: float, interval_end: float) -> list[StreamRow]:
    return [
        row
        for row in rows
        if (
            not row.excluded
            and row.local_bbox is not None
            and interval_start <= ((row.stream_y_start + row.stream_y_end) / 2) < interval_end
        )
    ]


def row_union_crop_bbox(
    block: ColumnBlock,
    block_rows: list[StreamRow],
    overlap: tuple[float, float],
) -> tuple[list[int] | None, list[str]]:
    interval_rows = rows_in_interval(block_rows, overlap[0], overlap[1])
    row_bboxes = [row.local_bbox for row in interval_rows if row.local_bbox is not None]
    if not row_bboxes:
        return None, []

    row_union = union_bboxes(row_bboxes)
    if row_union is None:
        return None, []

    return [
        block.content_bbox[0],
        row_union[1],
        block.content_bbox[2],
        row_union[3],
    ], [row.row_id for row in interval_rows]


def interval_local_y_end(block: ColumnBlock, overlap: tuple[float, float]) -> int:
    return block.content_bbox[1] + int(round(overlap[1] - block.stream_y_start))


def write_interval_crop_parts(
    *,
    run_dir: Path,
    blocks: list[ColumnBlock],
    rows_by_block: dict[str, list[StreamRow]],
    interval_start: float,
    interval_end: float,
    crop_padding: int,
    keep_crop_part_images: bool,
    directory_name: str,
    preview_name: str,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required. Run: uv sync --extra pdf") from exc

    candidate_dir = run_dir / directory_name
    candidate_dir.mkdir(parents=True, exist_ok=True)
    parts: list[dict[str, Any]] = []
    part_images: list[Path] = []

    for block in blocks:
        overlap = intersect_interval(interval_start, interval_end, block.stream_y_start, block.stream_y_end)
        if overlap is None:
            continue
        with Image.open(block.image_path) as img:
            width, height = img.size
            crop_basis = "interval_row_union"
            row_ids: list[str] = []
            local_crop_source_bbox, row_ids = row_union_crop_bbox(
                block,
                rows_by_block.get(block.block_id, []),
                overlap,
            )
            if local_crop_source_bbox is None:
                continue
            crop_bbox = pad_bbox(
                local_crop_source_bbox,
                crop_padding,
                width,
                height,
            )
            interval_y_end = max(0, min(height, interval_local_y_end(block, overlap)))
            crop_bbox[3] = min(crop_bbox[3], interval_y_end)
            if crop_bbox[2] <= crop_bbox[0] or crop_bbox[3] <= crop_bbox[1]:
                continue
            part_image = img.crop(tuple(crop_bbox))
            part_path = candidate_dir / f"part_{len(parts) + 1:02d}_{block.block_id}.png"
            part_image.save(part_path)
            part_images.append(part_path)

        parts.append(
            {
                "part_index": len(parts) + 1,
                "kind": "candidate_crop_part",
                "page": block.page,
                "column": block.column,
                "block_id": block.block_id,
                "source_image_path": block.image_path,
                "crop_image_path": str(part_path),
                "crop_image_deleted_after_preview": False,
                "local_crop_bbox": crop_bbox,
                "local_crop_basis": crop_basis,
                "local_crop_interval_y_end": interval_y_end,
                "included_row_ids": row_ids,
                "source_page_crop_bbox": source_page_bbox(crop_bbox, block.page_bbox),
                "stream_y_start": overlap[0],
                "stream_y_end": overlap[1],
            }
        )

    preview_path: str | None = None
    preview_saved = False
    if part_images:
        preview_path = str(candidate_dir / preview_name)
        loaded = [Image.open(path).convert("RGB") for path in part_images]
        try:
            max_width = max(image.width for image in loaded)
            total_height = sum(image.height for image in loaded) + (len(loaded) - 1) * 16
            preview = Image.new("RGB", (max_width, total_height), "white")
            draw = ImageDraw.Draw(preview)
            y = 0
            for image in loaded:
                preview.paste(image, (0, y))
                y += image.height
                if y < total_height:
                    draw.line([(0, y + 7), (max_width, y + 7)], fill=(200, 200, 200), width=2)
                    y += 16
            preview.save(preview_path)
            preview_saved = True
        finally:
            for image in loaded:
                image.close()

    if preview_saved and not keep_crop_part_images:
        for part, part_path in zip(parts, part_images, strict=False):
            if part_path.exists():
                part_path.unlink()
            part["deleted_crop_image_path"] = str(part_path)
            part["crop_image_path"] = None
            part["crop_image_deleted_after_preview"] = True

    return parts, preview_path


def next_question_anchor(
    selected_anchors: list[AnchorCandidate],
    current_anchor: AnchorCandidate,
) -> AnchorCandidate | None:
    for candidate in selected_anchors:
        if candidate.stream_y_start > current_anchor.stream_y_start:
            return candidate
    return None


def containing_set_header(
    selected_set_headers: list[SetHeaderAnchor],
    anchor: AnchorCandidate,
) -> SetHeaderAnchor | None:
    for set_header in selected_set_headers:
        if (
            set_header.start_question <= anchor.question_number <= set_header.end_question
            and set_header.stream_y_start <= anchor.stream_y_start
        ):
            return set_header
    return None


def next_set_header(
    selected_set_headers: list[SetHeaderAnchor],
    current_set: SetHeaderAnchor,
) -> SetHeaderAnchor | None:
    for candidate in selected_set_headers:
        if candidate.stream_y_start > current_set.stream_y_start:
            return candidate
    return None


def derive_end_from_assigned_rows(
    rows: list[StreamRow],
    interval_start: float,
    boundary_limit: float,
) -> tuple[float, str | None, str | None, str]:
    assigned_rows = rows_in_interval(rows, interval_start, boundary_limit)
    if not assigned_rows:
        return boundary_limit, None, None, "fallback-boundary-limit-no-assigned-row"

    end_row = max(assigned_rows, key=lambda row: (row.stream_y_end, row.stream_y_start, row.row_id))
    end_y = min(boundary_limit, max(interval_start + 1, end_row.stream_y_end))
    return end_y, f"end_{end_row.row_id}", end_row.text, "current-question-last-assigned-row"


def save_candidate_crops(
    *,
    run_dir: Path,
    blocks: list[ColumnBlock],
    rows: list[StreamRow],
    selected_anchors: list[AnchorCandidate],
    selected_set_headers: list[SetHeaderAnchor],
    crop_padding: int,
    keep_crop_part_images: bool,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if not blocks:
        return suggestions

    stream_end = max(block.stream_y_end for block in blocks)
    selected_anchors = sorted(selected_anchors, key=lambda item: item.stream_y_start)
    selected_set_headers = sorted(selected_set_headers, key=lambda item: item.stream_y_start)
    anchors_by_question = {anchor.question_number: anchor for anchor in selected_anchors}
    rows_by_block: dict[str, list[StreamRow]] = {}
    for row in rows:
        rows_by_block.setdefault(row.block_id, []).append(row)

    for set_header in selected_set_headers:
        first_question_anchor = anchors_by_question.get(set_header.start_question)
        if first_question_anchor is None or first_question_anchor.stream_y_start <= set_header.stream_y_start:
            continue

        directory_name = f"set_{set_header.start_question:02d}_{set_header.end_question:02d}_passage_candidate"
        parts, preview_path = write_interval_crop_parts(
            run_dir=run_dir,
            blocks=blocks,
            rows_by_block=rows_by_block,
            interval_start=set_header.stream_y_start,
            interval_end=first_question_anchor.stream_y_start,
            crop_padding=crop_padding,
            keep_crop_part_images=keep_crop_part_images,
            directory_name=directory_name,
            preview_name=f"set_{set_header.start_question:02d}_{set_header.end_question:02d}_passage_candidate_preview.png",
        )
        if not parts:
            continue
        suggestions.append(
            {
                "suggestion_id": f"set_{set_header.start_question:02d}_{set_header.end_question:02d}_passage",
                "kind": "candidate_passage_crop_suggestion",
                "verified": False,
                "label": "candidate",
                "start_question": set_header.start_question,
                "end_question": set_header.end_question,
                "start_anchor_id": set_header.anchor_id,
                "start_anchor_text": set_header.text,
                "end_anchor_id": first_question_anchor.anchor_id,
                "end_anchor_text": first_question_anchor.text,
                "boundary_end_reason": "first-question-anchor-in-set",
                "stream_y_start": set_header.stream_y_start,
                "stream_y_end": first_question_anchor.stream_y_start,
                "crosses_blocks": len({part["block_id"] for part in parts}) > 1,
                "candidate_preview_path": preview_path,
                "parts": parts,
                "provenance_note": "Candidate passage generated from a selected set header to the first question anchor; not verified text.",
            }
        )

    for anchor in selected_anchors:
        interval_start = anchor.stream_y_start
        set_header = containing_set_header(selected_set_headers, anchor)
        boundary_limit = stream_end
        boundary_limit_reason = "fallback-stream-end"
        boundary_limit_anchor_id: str | None = None
        boundary_limit_anchor_text: str | None = None

        if set_header is not None and anchor.question_number < set_header.end_question:
            next_in_set = anchors_by_question.get(anchor.question_number + 1)
            if next_in_set is not None and next_in_set.stream_y_start > interval_start:
                boundary_limit = next_in_set.stream_y_start
                boundary_limit_reason = "next-question-anchor-in-set"
                boundary_limit_anchor_id = next_in_set.anchor_id
                boundary_limit_anchor_text = next_in_set.text
            else:
                following_anchor = next_question_anchor(selected_anchors, anchor)
                if following_anchor is not None:
                    boundary_limit = following_anchor.stream_y_start
                    boundary_limit_reason = "fallback-next-selected-question-anchor"
                    boundary_limit_anchor_id = following_anchor.anchor_id
                    boundary_limit_anchor_text = following_anchor.text
        elif set_header is not None and anchor.question_number == set_header.end_question:
            following_set = next_set_header(selected_set_headers, set_header)
            if following_set is not None and following_set.stream_y_start > interval_start:
                boundary_limit = following_set.stream_y_start
                boundary_limit_reason = "next-set-header-anchor"
                boundary_limit_anchor_id = following_set.anchor_id
                boundary_limit_anchor_text = following_set.text
            else:
                following_anchor = next_question_anchor(selected_anchors, anchor)
                if following_anchor is not None:
                    boundary_limit = following_anchor.stream_y_start
                    boundary_limit_reason = "fallback-next-selected-question-anchor"
                    boundary_limit_anchor_id = following_anchor.anchor_id
                    boundary_limit_anchor_text = following_anchor.text
        else:
            following_anchor = next_question_anchor(selected_anchors, anchor)
            if following_anchor is not None:
                boundary_limit = following_anchor.stream_y_start
                boundary_limit_reason = "no-set-header-next-question-anchor"
                boundary_limit_anchor_id = following_anchor.anchor_id
                boundary_limit_anchor_text = following_anchor.text

        if boundary_limit <= interval_start:
            continue

        interval_end, end_anchor_id, end_anchor_text, boundary_end_reason = derive_end_from_assigned_rows(
            rows,
            interval_start,
            boundary_limit,
        )
        if interval_end <= interval_start:
            continue

        parts, preview_path = write_interval_crop_parts(
            run_dir=run_dir,
            blocks=blocks,
            rows_by_block=rows_by_block,
            interval_start=interval_start,
            interval_end=interval_end,
            crop_padding=crop_padding,
            keep_crop_part_images=keep_crop_part_images,
            directory_name=f"q{anchor.question_number:02d}_candidate",
            preview_name=f"q{anchor.question_number:02d}_candidate_preview.png",
        )
        if not parts:
            continue
        suggestions.append(
            {
                "suggestion_id": f"q{anchor.question_number:02d}",
                "kind": "candidate_question_crop_suggestion",
                "verified": False,
                "label": "candidate",
                "question_number": anchor.question_number,
                "set_header_anchor_id": set_header.anchor_id if set_header is not None else None,
                "set_start_question": set_header.start_question if set_header is not None else None,
                "set_end_question": set_header.end_question if set_header is not None else None,
                "start_anchor_id": anchor.anchor_id,
                "start_anchor_text": anchor.text,
                "end_anchor_id": end_anchor_id,
                "end_anchor_text": end_anchor_text,
                "end_anchor_type": "derived_current_question_end_row" if end_anchor_id else None,
                "boundary_end_reason": boundary_end_reason,
                "boundary_limit_reason": boundary_limit_reason,
                "boundary_limit_anchor_id": boundary_limit_anchor_id,
                "boundary_limit_anchor_text": boundary_limit_anchor_text,
                "boundary_limit_stream_y": boundary_limit,
                "stream_y_start": interval_start,
                "stream_y_end": interval_end,
                "crosses_blocks": len({part["block_id"] for part in parts}) > 1,
                "candidate_preview_path": preview_path,
                "parts": parts,
                "provenance_note": "Candidate generated from OCR anchors in virtual page-column reading order; not verified question text.",
            }
        )

    return suggestions


def save_annotated_blocks(
    run_dir: Path,
    blocks: list[ColumnBlock],
    rows: list[StreamRow],
    selected_anchors: list[AnchorCandidate],
    selected_set_headers: list[SetHeaderAnchor],
) -> list[str]:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return []

    rows_by_block: dict[str, list[StreamRow]] = {}
    for row in rows:
        rows_by_block.setdefault(row.block_id, []).append(row)
    selected_by_row = {anchor.row_id: anchor for anchor in selected_anchors}
    selected_set_by_row = {anchor.row_id: anchor for anchor in selected_set_headers}

    paths: list[str] = []
    for block in blocks:
        with Image.open(block.image_path) as img:
            annotated = img.convert("RGB")
        draw = ImageDraw.Draw(annotated)
        draw.rectangle(block.content_bbox, outline=(40, 120, 255), width=3)
        for row in rows_by_block.get(block.block_id, []):
            if row.local_bbox is None:
                continue
            if row.row_id in selected_set_by_row:
                color = (160, 70, 220)
                width = 4
                set_header = selected_set_by_row[row.row_id]
                label = f"set {set_header.start_question:02d}-{set_header.end_question:02d}"
                draw.text((row.local_bbox[0], max(0, row.local_bbox[1] - 18)), label, fill=color)
            elif row.row_id in selected_by_row:
                color = (220, 40, 40)
                width = 4
                label = f"q{selected_by_row[row.row_id].question_number:02d} candidate"
                draw.text((row.local_bbox[0], max(0, row.local_bbox[1] - 18)), label, fill=color)
            elif row.excluded:
                color = (150, 150, 150)
                width = 1
            else:
                color = (80, 180, 80)
                width = 1
            draw.rectangle(row.local_bbox, outline=color, width=width)
        out_path = run_dir / f"{block.block_id}_annotated.png"
        annotated.save(out_path)
        paths.append(str(out_path))
    return paths


def prepare_page_column_blocks(args: argparse.Namespace, run_dir: Path) -> list[RawBlock]:
    pages = parse_pages(args.pages)
    raw_blocks: list[RawBlock] = []
    for page in pages:
        print(f"Rendering page {page}...")
        page_image = render_pdf_page_cached(args.pdf, page, args.dpi, run_dir, args)
        for raw_block in crop_page_columns(page_image, run_dir, page, args):
            raw_blocks.append(
                RawBlock(
                    sequence_index=len(raw_blocks),
                    page=int(raw_block["page"]),
                    column=str(raw_block["column"]),
                    page_image_path=str(raw_block["page_image_path"]),
                    image_path=str(raw_block["image_path"]),
                    page_bbox=list(raw_block["page_bbox"]),
                    local_size=list(raw_block["local_size"]),
                )
            )
    return raw_blocks


def _ocr_error(raw_block: RawBlock, error: str) -> dict[str, Any]:
    return {
        "page": raw_block.page,
        "column": raw_block.column,
        "image_path": raw_block.image_path,
        "error": error,
    }


def _run_ocr_for_blocks_individually(
    raw_blocks: list[RawBlock],
    args: argparse.Namespace,
    run_dir: Path,
) -> tuple[list[OcrBlock], list[dict[str, Any]]]:
    ocr_blocks: list[OcrBlock] = []
    ocr_errors: list[dict[str, Any]] = []
    for raw_block in raw_blocks:
        print(f"Running PaddleOCR on page {raw_block.page} {raw_block.column}...")
        raw_rows, error = run_ocr_for_block(raw_block.ocr_input(), args, run_dir)
        if error:
            ocr_errors.append(_ocr_error(raw_block, error))
        ocr_blocks.append(OcrBlock(raw_block=raw_block, raw_rows=raw_rows, error=error))
    return ocr_blocks, ocr_errors


def run_ocr_for_blocks(
    raw_blocks: list[RawBlock],
    args: argparse.Namespace,
    run_dir: Path,
) -> tuple[list[OcrBlock], list[dict[str, Any]]]:
    if len(raw_blocks) <= 1:
        return _run_ocr_for_blocks_individually(raw_blocks, args, run_dir)

    print(f"Running PaddleOCR batch on {len(raw_blocks)} page-column blocks...")
    try:
        batch_results = run_paddleocr_batch([Path(raw_block.image_path) for raw_block in raw_blocks], args)
        if len(batch_results) != len(raw_blocks):
            raise ValueError("Batch OCR result count did not match input block count")
        ocr_blocks: list[OcrBlock] = []
        for raw_block, (_, payload) in zip(raw_blocks, batch_results, strict=True):
            raw_rows = write_ocr_block_artifacts(raw_block.ocr_input(), payload, args, run_dir)
            ocr_blocks.append(OcrBlock(raw_block=raw_block, raw_rows=raw_rows))
        return ocr_blocks, []
    except Exception as exc:  # noqa: BLE001 - unsupported batch OCR should preserve current behavior.
        print(f"Batch OCR unavailable; falling back to per-block OCR: {exc}")
        return _run_ocr_for_blocks_individually(raw_blocks, args, run_dir)


def build_stream_from_ocr_blocks(
    ocr_blocks: list[OcrBlock],
    args: argparse.Namespace,
) -> tuple[list[ColumnBlock], list[StreamRow]]:
    blocks: list[ColumnBlock] = []
    rows: list[StreamRow] = []
    stream_y = 0.0
    for ocr_block in sorted(ocr_blocks, key=lambda block: block.raw_block.sequence_index):
        block, block_rows = make_block_and_rows(ocr_block.raw_block.ocr_input(), ocr_block.raw_rows, stream_y, args)
        blocks.append(block)
        rows.extend(block_rows)
        stream_y = block.stream_y_end + args.stream_gap
    return blocks, rows


def processed_pages_from_ocr_blocks(pages: list[int], ocr_blocks: list[OcrBlock]) -> list[int]:
    blocks_by_page: dict[int, list[OcrBlock]] = {}
    for ocr_block in ocr_blocks:
        blocks_by_page.setdefault(ocr_block.raw_block.page, []).append(ocr_block)
    processed_pages: list[int] = []
    for page in pages:
        page_blocks = blocks_by_page.get(page, [])
        if len(page_blocks) == len(COLUMN_ORDER) and all(block.error is None for block in page_blocks):
            processed_pages.append(page)
    return processed_pages


def build_suggestions_payload(
    args: argparse.Namespace,
    run_dir: Path,
    blocks: list[ColumnBlock],
    rows: list[StreamRow],
    ocr_blocks: list[OcrBlock],
    ocr_errors: list[dict[str, Any]],
    *,
    interrupted: bool,
) -> dict[str, Any]:
    pages = parse_pages(args.pages)
    blocks_by_id = {block.block_id: block for block in blocks}
    set_header_candidates, selected_set_headers = detect_set_header_candidates(rows, blocks_by_id, args.min_anchor_score)
    anchor_candidates, selected_anchors = detect_anchor_candidates(
        rows,
        blocks_by_id,
        args.min_anchor_score,
        args.allow_weak_question_anchors,
    )
    suggestions = save_candidate_crops(
        run_dir=run_dir,
        blocks=blocks,
        rows=rows,
        selected_anchors=selected_anchors,
        selected_set_headers=selected_set_headers,
        crop_padding=args.crop_padding,
        keep_crop_part_images=args.keep_crop_part_images,
    )
    annotated_paths = (
        []
        if args.no_annotated_blocks
        else save_annotated_blocks(run_dir, blocks, rows, selected_anchors, selected_set_headers)
    )

    return {
        "artifact_type": "candidate_question_crop_suggestions",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "verified": False,
        "source": {
            "pdf": str(args.pdf),
            "pages": pages,
            "dpi": args.dpi,
        },
        "options": {
            "crop_top": args.crop_top,
            "crop_bottom": args.crop_bottom,
            "crop_left": args.crop_left,
            "crop_right": args.crop_right,
            "center_gutter": args.center_gutter,
            "content_padding": args.content_padding,
            "crop_padding": args.crop_padding,
            "keep_crop_part_images": args.keep_crop_part_images,
            "stream_gap": args.stream_gap,
            "min_anchor_score": args.min_anchor_score,
            "allow_weak_question_anchors": args.allow_weak_question_anchors,
            "include_raw_paddle_payload": args.include_raw_paddle_payload,
            "reuse_existing_images": args.reuse_existing_images,
            "paddle_lang": args.paddle_lang,
            "paddle_device": args.paddle_device,
            "paddle_cpu_threads": args.paddle_cpu_threads,
            "paddle_disable_mkldnn": args.paddle_disable_mkldnn,
            "paddle_text_recognition_batch_size": args.paddle_text_recognition_batch_size,
            "paddle_disable_pir": args.paddle_disable_pir,
            "paddle_disable_doc_preprocess": args.paddle_disable_doc_preprocess,
            "paddle_preimport_torch": args.paddle_preimport_torch,
            "paddle_preimport_paddle": args.paddle_preimport_paddle,
        },
        "model": {
            "reading_order": "page-left, page-right, next-page-left, next-page-right",
            "question_numbers": "candidate anchors only; question text is not verified",
            "set_headers": "selected LEET set headers can create passage intervals and last-question boundaries",
        },
        "status": "partial_interrupted" if interrupted else "complete",
        "interrupted": interrupted,
        "processed_pages": processed_pages_from_ocr_blocks(pages, ocr_blocks),
        "blocks": [asdict(block) for block in blocks],
        "rows": [asdict(row) for row in rows],
        "set_header_candidates": [asdict(anchor) for anchor in set_header_candidates],
        "selected_set_headers": [asdict(anchor) for anchor in selected_set_headers],
        "anchor_candidates": [asdict(anchor) for anchor in anchor_candidates],
        "selected_anchors": [asdict(anchor) for anchor in selected_anchors],
        "suggestions": suggestions,
        "annotated_block_paths": annotated_paths,
        "ocr_errors": ocr_errors,
    }


def build_stream(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    raw_blocks: list[RawBlock] = []
    ocr_blocks: list[OcrBlock] = []
    ocr_errors: list[dict[str, Any]] = []
    interrupted = False

    try:
        raw_blocks = prepare_page_column_blocks(args, run_dir)
        ocr_blocks, ocr_errors = run_ocr_for_blocks(raw_blocks, args, run_dir)
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted; writing partial suggestions for completed OCR blocks...")

    blocks, rows = build_stream_from_ocr_blocks(ocr_blocks, args)
    return build_suggestions_payload(
        args,
        run_dir,
        blocks,
        rows,
        ocr_blocks,
        ocr_errors,
        interrupted=interrupted,
    )


def write_suggestions(run_dir: Path, payload: dict[str, Any]) -> Path:
    out_path = run_dir / "suggestions.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def print_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    status = payload.get("status", "complete")
    status_label = "partial after interrupt" if status == "partial_interrupted" else "complete"
    print(f"\nQuestion crop suggestions {status_label}: {run_dir}")
    if payload.get("processed_pages"):
        print(f"- processed pages: {payload['processed_pages']}")
    print(f"- blocks: {len(payload['blocks'])}")
    print(f"- OCR rows: {len(payload['rows'])}")
    print(f"- set-header candidates: {len(payload['set_header_candidates'])}")
    print(f"- selected set headers: {len(payload['selected_set_headers'])}")
    print(f"- anchor candidates: {len(payload['anchor_candidates'])}")
    print(f"- selected anchors: {len(payload['selected_anchors'])}")
    passage_count = sum(1 for item in payload["suggestions"] if item["kind"] == "candidate_passage_crop_suggestion")
    question_count = sum(1 for item in payload["suggestions"] if item["kind"] == "candidate_question_crop_suggestion")
    print(f"- candidate suggestions: {len(payload['suggestions'])} ({passage_count} passage, {question_count} question)")
    if payload["ocr_errors"]:
        print(f"- OCR block errors: {len(payload['ocr_errors'])}")
    print(f"- suggestions: {run_dir / 'suggestions.json'}")
    print("\nAll crops are candidate suggestions for review, not verified question text.")


def main() -> int:
    args = parse_args()
    run_dir = make_run_dir(args.out_dir, args.run_id)
    payload = build_stream(args, run_dir)
    write_suggestions(run_dir, payload)
    print_summary(run_dir, payload)
    return 130 if payload.get("interrupted") else 0


if __name__ == "__main__":
    raise SystemExit(main())
