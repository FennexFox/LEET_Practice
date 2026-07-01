#!/usr/bin/env python
"""Run PaddleOCR on a rendered PDF page or image.

The script is diagnostic: it writes raw OCR text/JSON artifacts for verification,
but it does not write into `data/canonical/` or `data/reviews/`.

Example:
    uv run python tools/compare_ocr_engines.py \
        --pdf "data/raw_pdfs/leet-2026-verbal-even.pdf" \
        --page 1 \
        --split-columns \
        --paddle-device gpu:0 \
        --paddle-preimport-paddle
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImageTask:
    label: str
    path: Path


@dataclass(frozen=True)
class OcrResult:
    image_label: str
    image_path: str
    status: str
    elapsed_seconds: float
    text_path: str | None
    json_path: str | None
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PaddleOCR on one PDF page or image.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path, help="Input PDF path.")
    source.add_argument("--image", type=Path, help="Input image path.")

    parser.add_argument("--page", type=int, default=1, help="1-based PDF page number. Default: 1.")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI. Default: 300.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/ocr_compare"),
        help="Directory where OCR outputs are written.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional output run directory name. Defaults to timestamp.",
    )

    parser.add_argument(
        "--split-columns",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Split the page/image into left and right columns before OCR. Default: true.",
    )
    parser.add_argument(
        "--include-full-page",
        action="store_true",
        help="Also run OCR on the full rendered page/image in addition to column crops.",
    )
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

    return parser.parse_args()


def make_run_dir(base_dir: Path, run_id: str | None) -> Path:
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def render_pdf_page(pdf_path: Path, page_1based: int, dpi: int, run_dir: Path) -> Path:
    if page_1based <= 0:
        raise ValueError("--page must be 1 or greater.")
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required. Run: uv sync --extra pdf") from exc

    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    page_index = page_1based - 1
    out_path = run_dir / f"page_{page_1based:03d}_{dpi}dpi.png"
    with fitz.open(pdf_path) as doc:
        if page_index >= len(doc):
            raise ValueError(f"PDF has {len(doc)} pages, but page {page_1based} was requested.")

        page = doc[page_index]
        zoom = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(out_path)
    return out_path


def prepare_image_source(image_path: Path, run_dir: Path) -> Path:
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    suffix = image_path.suffix.lower() or ".png"
    out_path = run_dir / f"input_image{suffix}"
    shutil.copy2(image_path, out_path)
    return out_path


def crop_columns(
    image_path: Path,
    run_dir: Path,
    *,
    crop_top: float,
    crop_bottom: float,
    crop_left: float,
    crop_right: float,
    center_gutter: float,
) -> list[ImageTask]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required. Run: uv sync --extra pdf") from exc

    with Image.open(image_path) as img:
        width, height = img.size

        top = int(height * crop_top)
        bottom = int(height * crop_bottom)
        left_margin = int(width * crop_left)
        right_margin = int(width * crop_right)
        mid = int(width * 0.5)
        gutter_px = int(width * center_gutter)

        if not (0 <= left_margin < mid - gutter_px < mid + gutter_px < right_margin <= width):
            raise ValueError("Invalid crop ratios. Check crop margins and center gutter.")
        if not (0 <= top < bottom <= height):
            raise ValueError("Invalid vertical crop ratios.")

        left_img = img.crop((left_margin, top, mid - gutter_px, bottom))
        right_img = img.crop((mid + gutter_px, top, right_margin, bottom))

        left_path = run_dir / "crop_left.png"
        right_path = run_dir / "crop_right.png"
        left_img.save(left_path)
        right_img.save(right_path)

    return [ImageTask("left", left_path), ImageTask("right", right_path)]


def safe_jsonable(value: Any) -> Any:
    """Convert OCR library return values into JSON-friendly data."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): safe_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [safe_jsonable(item) for item in value]

    if hasattr(value, "tolist"):
        try:
            return safe_jsonable(value.tolist())
        except Exception:
            pass

    json_attr = getattr(value, "json", None)
    if json_attr is not None:
        try:
            json_value = json_attr() if callable(json_attr) else json_attr
            return safe_jsonable(json_value)
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return safe_jsonable(vars(value))
        except Exception:
            pass

    return repr(value)


def configure_paddle_runtime(args: argparse.Namespace) -> dict[str, str]:
    """Set Paddle runtime flags before importing PaddleOCR."""
    applied: dict[str, str] = {}
    if args.paddle_disable_mkldnn:
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["FLAGS_use_onednn"] = "0"
        applied["FLAGS_use_mkldnn"] = "0"
        applied["FLAGS_use_onednn"] = "0"
    if args.paddle_disable_pir:
        os.environ["FLAGS_enable_pir_api"] = "0"
        applied["FLAGS_enable_pir_api"] = "0"
    return applied


_PADDLE_OCR_CACHE: dict[tuple[Any, ...], Any] = {}


def build_paddleocr(args: argparse.Namespace) -> Any:
    configure_paddle_runtime(args)

    # On Windows, native DLL load order matters. The OCR-oriented GPU setup that
    # worked most reliably was Torch CPU -> Paddle GPU -> PaddleOCR.
    if args.paddle_preimport_torch:
        try:
            import torch  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "--paddle-preimport-torch is enabled, but torch is not installed. "
                "Install torch or rerun with --no-paddle-preimport-torch."
            ) from exc

    if args.paddle_preimport_paddle:
        try:
            import paddle  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "--paddle-preimport-paddle is enabled, but paddle is not installed. "
                "Install paddlepaddle/paddlepaddle-gpu or rerun with --no-paddle-preimport-paddle."
            ) from exc

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("paddleocr is required. Run: uv sync --extra ocr") from exc

    constructor_params = inspect.signature(PaddleOCR).parameters
    kwargs: dict[str, Any] = {"lang": str(args.paddle_lang)}

    # PaddleOCR constructor arguments differ across releases. Only pass an option
    # when the installed version advertises it.
    if args.paddle_device and "device" in constructor_params:
        kwargs["device"] = args.paddle_device
    if "cpu_threads" in constructor_params:
        kwargs["cpu_threads"] = args.paddle_cpu_threads
    text_recognition_batch_size = getattr(args, "paddle_text_recognition_batch_size", None)
    if text_recognition_batch_size is not None:
        if text_recognition_batch_size <= 0:
            raise ValueError("--paddle-text-recognition-batch-size must be positive.")
        if "text_recognition_batch_size" in constructor_params:
            kwargs["text_recognition_batch_size"] = text_recognition_batch_size
        elif "rec_batch_num" in constructor_params:
            kwargs["rec_batch_num"] = text_recognition_batch_size
    if args.paddle_disable_mkldnn and "enable_mkldnn" in constructor_params:
        kwargs["enable_mkldnn"] = False
    if args.paddle_disable_doc_preprocess:
        for key in (
            "use_doc_orientation_classify",
            "use_doc_unwarping",
            "use_textline_orientation",
            "use_angle_cls",
        ):
            if key in constructor_params:
                kwargs[key] = False

    return PaddleOCR(**kwargs)


def get_paddleocr(args: argparse.Namespace) -> Any:
    cache_key = (
        str(args.paddle_lang),
        args.paddle_device,
        args.paddle_cpu_threads,
        getattr(args, "paddle_text_recognition_batch_size", None),
        args.paddle_disable_mkldnn,
        args.paddle_disable_pir,
        args.paddle_disable_doc_preprocess,
        args.paddle_preimport_torch,
        args.paddle_preimport_paddle,
    )
    if cache_key not in _PADDLE_OCR_CACHE:
        _PADDLE_OCR_CACHE[cache_key] = build_paddleocr(args)
    return _PADDLE_OCR_CACHE[cache_key]


def run_paddleocr(image_path: Path, args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    runtime_flags = configure_paddle_runtime(args)
    ocr = get_paddleocr(args)

    # PaddleOCR 3.x favors predict(); older examples often use ocr(). Support both.
    if hasattr(ocr, "predict"):
        try:
            result = ocr.predict(str(image_path))
        except TypeError:
            result = ocr.ocr(str(image_path))
    else:
        result = ocr.ocr(str(image_path))

    payload_raw = safe_jsonable(result)
    rows = extract_paddle_rows(payload_raw)
    text_output = "\n".join(format_paddle_row(row) for row in rows)
    if not text_output.strip():
        text_output = json.dumps(payload_raw, ensure_ascii=False, indent=2)

    payload = {
        "engine": "paddleocr",
        "language": str(args.paddle_lang),
        "runtime_flags": runtime_flags,
        "rows": rows,
        "raw": payload_raw,
    }
    return text_output, payload


def format_paddle_row(row: dict[str, Any]) -> str:
    text = str(row.get("text", ""))
    confidence = row.get("confidence")
    if isinstance(confidence, int | float):
        return f"{confidence:.3f}\t{text}"
    return text


def extract_paddle_rows(payload: Any) -> list[dict[str, Any]]:
    """Best-effort text extraction across PaddleOCR return formats."""
    rows: list[dict[str, Any]] = []

    def add_row(text: Any, confidence: Any = None, box: Any = None) -> None:
        text_value = str(text).strip()
        if not text_value:
            return
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        rows.append({"text": text_value, "confidence": confidence_value, "box": safe_jsonable(box)})

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("res"), dict):
                visit(node["res"])
                return

            rec_texts = node.get("rec_texts")
            if isinstance(rec_texts, list):
                scores = node.get("rec_scores") or node.get("scores") or []
                boxes = node.get("rec_polys") or node.get("rec_boxes") or node.get("dt_polys") or []
                for index, text in enumerate(rec_texts):
                    score = scores[index] if index < len(scores) else None
                    box = boxes[index] if index < len(boxes) else None
                    add_row(text, score, box)
                return

            if "text" in node or "transcription" in node:
                add_row(
                    node.get("text", node.get("transcription")),
                    node.get("confidence", node.get("score")),
                    node.get("box", node.get("points")),
                )
                return

            for value in node.values():
                visit(value)
            return

        if isinstance(node, list | tuple):
            # Legacy PaddleOCR format: [box, (text, score)]
            if len(node) == 2 and isinstance(node[1], list | tuple) and len(node[1]) >= 2:
                possible_text = node[1][0]
                possible_score = node[1][1]
                if isinstance(possible_text, str):
                    add_row(possible_text, possible_score, node[0])
                    return
            for item in node:
                visit(item)

    visit(payload)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("text", "")), json.dumps(row.get("box"), ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def write_text_and_json(
    *,
    run_dir: Path,
    image_label: str,
    text: str,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    text_path = run_dir / f"{image_label}.paddleocr.txt"
    json_path = run_dir / f"{image_label}.paddleocr.json"
    text_path.write_text(text, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return text_path, json_path


def run_task(image_task: ImageTask, run_dir: Path, args: argparse.Namespace) -> OcrResult:
    started = time.perf_counter()
    try:
        text, payload = run_paddleocr(image_task.path, args)
        text_path, json_path = write_text_and_json(
            run_dir=run_dir,
            image_label=image_task.label,
            text=text,
            payload={
                "image_label": image_task.label,
                "image_path": str(image_task.path),
                **payload,
            },
        )
        return OcrResult(
            image_label=image_task.label,
            image_path=str(image_task.path),
            status="ok",
            elapsed_seconds=time.perf_counter() - started,
            text_path=str(text_path),
            json_path=str(json_path),
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic script should keep going.
        error_path = run_dir / f"{image_task.label}.paddleocr.error.txt"
        error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        error_path.write_text(error_text, encoding="utf-8")
        return OcrResult(
            image_label=image_task.label,
            image_path=str(image_task.path),
            status="error",
            elapsed_seconds=time.perf_counter() - started,
            text_path=str(error_path),
            json_path=None,
            error=str(exc),
        )


def write_manifest(run_dir: Path, args: argparse.Namespace, image_tasks: list[ImageTask], results: list[OcrResult]) -> None:
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "pdf": str(args.pdf) if args.pdf else None,
            "image": str(args.image) if args.image else None,
            "page": args.page,
            "dpi": args.dpi,
        },
        "options": {
            "split_columns": args.split_columns,
            "include_full_page": args.include_full_page,
            "crop_top": args.crop_top,
            "crop_bottom": args.crop_bottom,
            "crop_left": args.crop_left,
            "crop_right": args.crop_right,
            "center_gutter": args.center_gutter,
            "paddle_lang": args.paddle_lang,
            "paddle_device": args.paddle_device,
            "paddle_cpu_threads": args.paddle_cpu_threads,
            "paddle_text_recognition_batch_size": args.paddle_text_recognition_batch_size,
            "paddle_disable_mkldnn": args.paddle_disable_mkldnn,
            "paddle_disable_pir": args.paddle_disable_pir,
            "paddle_disable_doc_preprocess": args.paddle_disable_doc_preprocess,
            "paddle_preimport_torch": args.paddle_preimport_torch,
            "paddle_preimport_paddle": args.paddle_preimport_paddle,
        },
        "images": [{"label": task.label, "path": str(task.path)} for task in image_tasks],
        "results": [result.__dict__ for result in results],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(run_dir: Path, results: list[OcrResult]) -> None:
    print(f"\nPaddleOCR complete: {run_dir}")
    print("\nResults:")
    for result in results:
        status = "OK" if result.status == "ok" else "ERROR"
        print(f"- {status:5} {result.image_label:10} {result.elapsed_seconds:7.2f}s  {result.text_path}")
        if result.error:
            print(f"  error: {result.error}")


def main() -> int:
    args = parse_args()
    run_dir = make_run_dir(args.out_dir, args.run_id)

    if args.pdf:
        source_image = render_pdf_page(args.pdf, args.page, args.dpi, run_dir)
    else:
        source_image = prepare_image_source(args.image, run_dir)

    image_tasks: list[ImageTask] = []
    if args.include_full_page or not args.split_columns:
        image_tasks.append(ImageTask("full", source_image))
    if args.split_columns:
        image_tasks.extend(
            crop_columns(
                source_image,
                run_dir,
                crop_top=args.crop_top,
                crop_bottom=args.crop_bottom,
                crop_left=args.crop_left,
                crop_right=args.crop_right,
                center_gutter=args.center_gutter,
            )
        )

    results: list[OcrResult] = []
    for task in image_tasks:
        print(f"Running PaddleOCR on {task.label} ({task.path})...")
        results.append(run_task(task, run_dir, args))

    write_manifest(run_dir, args, image_tasks, results)
    print_summary(run_dir, results)

    return 0 if all(result.status == "ok" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
