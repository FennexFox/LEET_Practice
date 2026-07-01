"""Command line entrypoint for LEET Practice."""

from __future__ import annotations

import importlib.util
import re
import sys
from ipaddress import ip_address
from pathlib import Path
from types import ModuleType

import typer
from rich.console import Console

from leet_practice import __version__
from leet_practice.verification import (
    VerificationError,
    initialize_review_state,
    promote_verified as promote_verified_records,
    review_state_path,
    serve_review_workbench,
)

app = typer.Typer(help="Local-first LEET practice and wrong-answer review tools.")
console = Console()
DEFAULT_DATA_ROOT = Path("data")
DEFAULT_ARTIFACTS_ROOT = Path("artifacts/question_crop_suggestions")


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _resolve_exam_id(arg_value: str | None, option_value: str | None) -> str:
    if arg_value and option_value and arg_value != option_value:
        console.print("[red]EXAM_ID and --exam-id disagree.[/red]")
        raise typer.Exit(1)
    exam_id = arg_value or option_value
    if not exam_id:
        console.print("[red]Missing EXAM_ID.[/red]")
        raise typer.Exit(1)
    return exam_id


def _default_pdf_path(exam_id: str, data_root: Path) -> Path:
    return data_root / "raw_pdfs" / f"{exam_id}.pdf"


def _latest_suggestions_path(exam_id: str, artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT) -> Path:
    candidates = [
        path
        for path in artifacts_root.glob(f"{exam_id}*/suggestions.json")
        if path.is_file()
    ]
    if not candidates:
        console.print(
            f"[red]No suggestions.json found for {exam_id} under {artifacts_root}.[/red]\n"
            "Pass --suggestions explicitly or run: leet-practice ocr EXAM_ID PAGES"
        )
        raise typer.Exit(1)
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_suggest_question_crops() -> ModuleType:
    tools_dir = Path(__file__).resolve().parents[2] / "tools"
    module_path = tools_dir / "suggest_question_crops.py"
    if not module_path.exists():
        console.print(f"[red]OCR crop suggestion tool not found:[/red] {module_path}")
        raise typer.Exit(1)
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    spec = importlib.util.spec_from_file_location("suggest_question_crops", module_path)
    if spec is None or spec.loader is None:
        console.print(f"[red]Failed to load OCR crop suggestion tool:[/red] {module_path}")
        raise typer.Exit(1)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _default_run_id(exam_id: str, pages: str, tool: ModuleType) -> str:
    try:
        parsed_pages = tool.parse_pages(pages)
    except ValueError:
        page_slug = re.sub(r"[^A-Za-z0-9]+", "-", pages).strip("-")
        return f"{exam_id}-p{page_slug}"
    if not parsed_pages:
        return f"{exam_id}-p{re.sub(r'[^A-Za-z0-9]+', '-', pages).strip('-')}"
    if parsed_pages == list(range(parsed_pages[0], parsed_pages[-1] + 1)):
        page_part = f"p{parsed_pages[0]:03d}-{parsed_pages[-1]:03d}"
    else:
        page_part = "p" + "-".join(f"{page:03d}" for page in parsed_pages)
    return f"{exam_id}-{page_part}"


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show package version and exit."),
) -> None:
    if version:
        console.print(f"leet-practice {__version__}")
        raise typer.Exit()


@app.command()
def scaffold_info() -> None:
    """Print the intended local data layout."""

    console.print("[bold]LEET Practice data layout[/bold]")
    console.print("- data/raw_pdfs/: local official PDFs")
    console.print("- data/rendered_pages/: rendered page images")
    console.print("- data/ocr/: raw OCR outputs")
    console.print("- data/verification/: human verification drafts")
    console.print("- data/canonical/: verified local exam data")
    console.print("- data/attempts/: personal attempt records")
    console.print("- data/reviews/: wrong-answer reviews")


def _run_ocr(
    exam_id: str,
    pages: str,
    *,
    pdf: Path | None,
    data_root: Path,
    out_dir: Path,
    run_id: str | None,
    paddle_device: str | None,
    paddle_text_recognition_batch_size: int | None,
    paddle_preimport_paddle: bool,
) -> None:
    tool = _load_suggest_question_crops()
    pdf_path = pdf or _default_pdf_path(exam_id, data_root)
    if not pdf_path.exists():
        console.print(
            f"[red]PDF not found:[/red] {pdf_path}\n"
            "Pass --pdf explicitly or place the file at data/raw_pdfs/EXAM_ID.pdf."
        )
        raise typer.Exit(1)
    actual_run_id = run_id or _default_run_id(exam_id, pages, tool)
    argv = [
        "--pdf",
        str(pdf_path),
        "--pages",
        pages,
        "--out-dir",
        str(out_dir),
        "--run-id",
        actual_run_id,
    ]
    if paddle_device:
        argv.extend(["--paddle-device", paddle_device])
    if paddle_text_recognition_batch_size is not None:
        argv.extend(["--paddle-text-recognition-batch-size", str(paddle_text_recognition_batch_size)])
    if paddle_preimport_paddle:
        argv.append("--paddle-preimport-paddle")

    args = tool.parse_args(argv)
    run_dir = tool.make_run_dir(args.out_dir, args.run_id)
    payload = tool.build_stream(args, run_dir)
    tool.write_suggestions(run_dir, payload)
    tool.print_summary(run_dir, payload)
    if payload.get("interrupted"):
        raise typer.Exit(130)


@app.command("ocr")
def ocr_command(
    exam_id: str = typer.Argument(..., metavar="EXAM_ID", help="Exam ID, for example leet-2026-verbal-even."),
    pages: str = typer.Argument(..., metavar="PAGES", help="1-based pages, for example 1-10 or 1,3,5-7."),
    pdf: Path | None = typer.Option(None, "--pdf", exists=True, help="Input PDF. Defaults to data/raw_pdfs/EXAM_ID.pdf."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root used for the default PDF path."),
    out_dir: Path = typer.Option(DEFAULT_ARTIFACTS_ROOT, "--out-dir", help="Directory where candidate suggestions are written."),
    run_id: str | None = typer.Option(None, "--run-id", help="Output run directory name. Defaults to EXAM_ID plus page range."),
    paddle_device: str | None = typer.Option(None, "--paddle-device", help="Optional PaddleOCR device, for example cpu or gpu:0."),
    paddle_text_recognition_batch_size: int | None = typer.Option(
        None,
        "--paddle-text-recognition-batch-size",
        help="Optional PaddleOCR text-recognition batch size.",
    ),
    paddle_preimport_paddle: bool = typer.Option(
        False,
        "--paddle-preimport-paddle",
        help="Import paddle before PaddleOCR for GPU-oriented Windows setups.",
    ),
) -> None:
    """Generate OCR-based candidate crop suggestions."""

    _run_ocr(
        exam_id,
        pages,
        pdf=pdf,
        data_root=data_root,
        out_dir=out_dir,
        run_id=run_id,
        paddle_device=paddle_device,
        paddle_text_recognition_batch_size=paddle_text_recognition_batch_size,
        paddle_preimport_paddle=paddle_preimport_paddle,
    )


def _run_review_crops(
    exam_id: str,
    *,
    suggestions: Path | None,
    data_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    no_open: bool = False,
    init_only: bool = False,
    overwrite: bool = False,
    refresh_preserving_edits: bool = False,
    enable_spacing_cleanup: bool = False,
    enable_morphology_checks: bool = False,
    unsafe_allow_remote: bool = False,
) -> None:
    suggestions_path = suggestions or _latest_suggestions_path(exam_id)
    try:
        if overwrite and refresh_preserving_edits:
            console.print("[red]--overwrite and --refresh-preserving-edits cannot be combined.[/red]")
            raise typer.Exit(1)
        state = initialize_review_state(
            exam_id,
            suggestions_path,
            data_root=data_root,
            overwrite=overwrite,
            refresh_preserving_edits=refresh_preserving_edits,
            enable_spacing_cleanup=enable_spacing_cleanup,
            enable_morphology_checks=enable_morphology_checks,
        )
    except VerificationError as exc:
        console.print(f"[red]Verification setup failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"Suggestions: {suggestions_path}")
    state_path = review_state_path(exam_id, data_root=data_root)
    console.print(f"Review state: {state_path}")
    console.print(f"Candidates: {len(state.candidates)}")
    if init_only:
        return

    if not _is_loopback_host(host) and not unsafe_allow_remote:
        console.print(
            "[red]Refusing to bind the unauthenticated workbench to a non-loopback host.[/red]\n"
            "Use --unsafe-allow-remote only on a trusted network."
        )
        raise typer.Exit(1)

    url = f"http://{host}:{port}/"
    console.print(f"Starting local verification workbench: {url}")
    console.print("Press Ctrl+C to stop.")
    try:
        serve_review_workbench(
            exam_id,
            data_root=data_root,
            host=host,
            port=port,
            open_browser=not no_open,
        )
    except KeyboardInterrupt:
        console.print("\nStopped verification workbench.")
    except OSError as exc:
        console.print(f"[red]Failed to start workbench:[/red] {exc}")
        raise typer.Exit(1) from exc

@app.command("verify")
def verify_command(
    exam_id_arg: str | None = typer.Argument(None, metavar="EXAM_ID", help="Exam ID for the verification workspace."),
    exam_id_option: str | None = typer.Option(None, "--exam-id", help="Legacy exam ID option.", hidden=True),
    suggestions: Path | None = typer.Option(
        None,
        "--suggestions",
        exists=True,
        help="Path to suggestions.json. Defaults to the latest artifacts/question_crop_suggestions/EXAM_ID*/suggestions.json.",
    ),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
    host: str = typer.Option("127.0.0.1", "--host", help="Local bind host."),
    port: int = typer.Option(8765, "--port", help="Local bind port."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open the browser automatically."),
    init_only: bool = typer.Option(False, "--init-only", help="Initialize review state without starting the server."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Rebuild review state from suggestions.json."),
    refresh_preserving_edits: bool = typer.Option(
        False,
        "--refresh-preserving-edits",
        help="Rebuild OCR-derived fields while preserving manually edited review fields for matching candidates.",
    ),
    enable_spacing_cleanup: bool = typer.Option(
        False,
        "--enable-spacing-cleanup",
        help="Apply optional local Korean spacing cleanup to OCR drafts when a backend is installed.",
    ),
    enable_morphology_checks: bool = typer.Option(
        False,
        "--enable-morphology-checks",
        help="Run optional Kiwi/kiwipiepy morphology checks for OCR draft warnings when installed.",
    ),
    unsafe_allow_remote: bool = typer.Option(
        False,
        "--unsafe-allow-remote",
        help="Allow binding the unauthenticated workbench to a non-loopback host.",
    ),
) -> None:
    """Review OCR crop suggestions in a local browser workbench."""

    exam_id = _resolve_exam_id(exam_id_arg, exam_id_option)
    _run_review_crops(
        exam_id,
        suggestions=suggestions,
        data_root=data_root,
        host=host,
        port=port,
        no_open=no_open,
        init_only=init_only,
        overwrite=overwrite,
        refresh_preserving_edits=refresh_preserving_edits,
        enable_spacing_cleanup=enable_spacing_cleanup,
        enable_morphology_checks=enable_morphology_checks,
        unsafe_allow_remote=unsafe_allow_remote,
    )


@app.command("review-crops", hidden=True)
def review_crops_command(
    exam_id_arg: str | None = typer.Argument(None, metavar="EXAM_ID", help="Exam ID for the verification workspace."),
    exam_id_option: str | None = typer.Option(None, "--exam-id", help="Exam ID for the verification workspace."),
    suggestions: Path | None = typer.Option(
        None,
        "--suggestions",
        exists=True,
        help="Path to suggestions.json. Defaults to the latest artifacts/question_crop_suggestions/EXAM_ID*/suggestions.json.",
    ),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
    host: str = typer.Option("127.0.0.1", "--host", help="Local bind host."),
    port: int = typer.Option(8765, "--port", help="Local bind port."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open the browser automatically."),
    init_only: bool = typer.Option(False, "--init-only", help="Initialize review state without starting the server."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Rebuild review state from suggestions.json."),
    refresh_preserving_edits: bool = typer.Option(
        False,
        "--refresh-preserving-edits",
        help="Rebuild OCR-derived fields while preserving manually edited review fields for matching candidates.",
    ),
    enable_spacing_cleanup: bool = typer.Option(
        False,
        "--enable-spacing-cleanup",
        help="Apply optional local Korean spacing cleanup to OCR drafts when a backend is installed.",
    ),
    enable_morphology_checks: bool = typer.Option(
        False,
        "--enable-morphology-checks",
        help="Run optional Kiwi/kiwipiepy morphology checks for OCR draft warnings when installed.",
    ),
    unsafe_allow_remote: bool = typer.Option(
        False,
        "--unsafe-allow-remote",
        help="Allow binding the unauthenticated workbench to a non-loopback host.",
    ),
) -> None:
    """Review OCR crop suggestions in a local browser workbench."""

    exam_id = _resolve_exam_id(exam_id_arg, exam_id_option)
    _run_review_crops(
        exam_id,
        suggestions=suggestions,
        data_root=data_root,
        host=host,
        port=port,
        no_open=no_open,
        init_only=init_only,
        overwrite=overwrite,
        refresh_preserving_edits=refresh_preserving_edits,
        enable_spacing_cleanup=enable_spacing_cleanup,
        enable_morphology_checks=enable_morphology_checks,
        unsafe_allow_remote=unsafe_allow_remote,
    )


def _run_promote_verified(exam_id: str, *, data_root: Path) -> None:
    try:
        passage_path, question_path, passage_count, question_count = promote_verified_records(
            exam_id,
            data_root=data_root,
        )
    except VerificationError as exc:
        console.print(f"[red]Promotion failed:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    console.print(f"Promoted {passage_count} passages -> {passage_path}")
    console.print(f"Promoted {question_count} questions -> {question_path}")


@app.command("promote")
def promote_command(
    exam_id_arg: str | None = typer.Argument(None, metavar="EXAM_ID", help="Exam ID to promote."),
    exam_id_option: str | None = typer.Option(None, "--exam-id", help="Legacy exam ID option.", hidden=True),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
) -> None:
    """Promote accepted verification drafts into canonical JSONL files."""

    exam_id = _resolve_exam_id(exam_id_arg, exam_id_option)
    _run_promote_verified(exam_id, data_root=data_root)


@app.command("promote-verified", hidden=True)
def promote_verified_command(
    exam_id_arg: str | None = typer.Argument(None, metavar="EXAM_ID", help="Exam ID to promote."),
    exam_id_option: str | None = typer.Option(None, "--exam-id", help="Exam ID to promote."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
) -> None:
    """Promote accepted verification drafts into canonical JSONL files."""

    exam_id = _resolve_exam_id(exam_id_arg, exam_id_option)
    _run_promote_verified(exam_id, data_root=data_root)
