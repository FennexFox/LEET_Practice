"""Command line entrypoint for LEET Practice."""

from __future__ import annotations

import json
from ipaddress import ip_address
from pathlib import Path

import typer
from rich.console import Console

from leet_practice import __version__
from leet_practice import attempt_review as attempt_review_workflow
from leet_practice import ocr_crops
from leet_practice import retry_pdf as retry_pdf_workflow
from leet_practice.ocr_benchmark import benchmark_record, write_benchmark_summary
from leet_practice.verification import (
    VerificationError,
    initialize_review_state,
    promote_verified as promote_verified_records,
    review_state_path,
    serve_review_workbench,
)

app = typer.Typer(help="Local-first LEET practice and wrong-answer review tools.")
attempt_review_app = typer.Typer(help="Attempt grading, self-review, and assistant feedback handoff.")
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
    if not artifacts_root.exists():
        candidates: list[Path] = []
    else:
        candidates = [
            suggestions_path
            for run_dir in artifacts_root.iterdir()
            if run_dir.is_dir() and (run_dir.name == exam_id or run_dir.name.startswith(f"{exam_id}-p"))
            for suggestions_path in [run_dir / "suggestions.json"]
            if suggestions_path.is_file()
        ]
    if not candidates:
        console.print(
            f"[red]No suggestions.json found for {exam_id} under {artifacts_root}.[/red]\n"
            "Pass --suggestions explicitly or run: leet-practice ocr EXAM_ID PAGES"
        )
        raise typer.Exit(1)
    return max(candidates, key=lambda path: path.stat().st_mtime)

def _default_run_id(exam_id: str, parsed_pages: list[int]) -> str:
    if not parsed_pages:
        return f"{exam_id}-p"
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


@app.command("retry-pdf")
def retry_pdf_command(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of automatically selected questions."),
    tag: list[str] = typer.Option([], "--tag", help="Primary tag to include. Repeat for multiple tags."),
    year: list[int] = typer.Option([], "--year", help="Exam year to include. Repeat for multiple years."),
    section: list[str] = typer.Option([], "--section", help="Exam section to include. Repeat for multiple sections."),
    include_holdout: bool = typer.Option(False, "--include-holdout", help="Allow holdout questions to be selected."),
    review_file: list[Path] = typer.Option(
        [],
        "--review-file",
        help="Select a review record explicitly. Repeat to preserve a manual question order.",
    ),
    title: str = typer.Option("LEET 오답 재풀이", "--title", help="Title printed on the retry workbook."),
    output: Path | None = typer.Option(None, "--output", help="Output PDF path."),
    font: Path | None = typer.Option(None, "--font", help="Korean TrueType/OpenType font path."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
) -> None:
    """Create a printable wrong-answer retry workbook and answer appendix."""

    try:
        bundle = retry_pdf_workflow.create_retry_pdf_bundle(
            data_root=data_root,
            review_files=review_file,
            limit=limit,
            tags=tag,
            years=year,
            sections=section,
            include_holdout=include_holdout,
            title=title,
            output_path=output,
            font_path=font,
        )
    except retry_pdf_workflow.RetryPdfError as exc:
        console.print(f"[red]Retry PDF generation failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"PDF: {bundle.pdf_path}")
    console.print(f"Manifest: {bundle.manifest_path}")


def _run_attempt_review_create(
    attempt_id: str,
    exam_id: str,
    answers: str,
    *,
    data_root: Path,
    mode: str,
    notes: str | None,
    overwrite: bool,
) -> None:
    try:
        attempt = attempt_review_workflow.create_attempt_record(
            attempt_id,
            exam_id,
            answers,
            data_root=data_root,
            mode=mode,
            notes=notes,
            overwrite=overwrite,
        )
    except attempt_review_workflow.AttemptReviewError as exc:
        console.print(f"[red]Attempt creation failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Attempt: {attempt_review_workflow.attempt_path(attempt.id, data_root=data_root)}")
    console.print(f"Answers: {len(attempt.answers)}")


@attempt_review_app.command("create")
def attempt_review_create_command(
    attempt_id: str = typer.Argument(..., metavar="ATTEMPT_ID", help="Attempt ID to store under data/attempts/."),
    exam_id: str = typer.Argument(..., metavar="EXAM_ID", help="Canonical exam ID."),
    answers: str = typer.Option(..., "--answers", help='Answer string, for example "22542 52323".'),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
    mode: str = typer.Option("real", "--mode", help="Attempt mode: real, review, or partial."),
    notes: str | None = typer.Option(None, "--notes", help="Optional attempt note."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing attempt record."),
) -> None:
    """Create an attempt record from a selected-answer string."""

    _run_attempt_review_create(
        attempt_id,
        exam_id,
        answers,
        data_root=data_root,
        mode=mode,
        notes=notes,
        overwrite=overwrite,
    )


def _run_attempt_review_grade(attempt_id: str, *, data_root: Path) -> None:
    try:
        state = attempt_review_workflow.initialize_attempt_reviews(attempt_id, data_root=data_root)
    except attempt_review_workflow.AttemptReviewError as exc:
        console.print(f"[red]Attempt grading failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Answer key: {state.answer_key_source}")
    console.print(f"Score: {state.score}/{state.total}")
    wrong = ", ".join(str(question_no) for question_no in state.wrong_question_numbers) or "none"
    console.print(f"Wrong questions: {wrong}")
    console.print(f"Review directory: {attempt_review_workflow.attempt_reviews_dir(attempt_id, data_root=data_root)}")


@attempt_review_app.command("grade")
def attempt_review_grade_command(
    attempt_id: str = typer.Argument(..., metavar="ATTEMPT_ID", help="Attempt ID."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
) -> None:
    """Grade an attempt and create review files for wrong answers."""

    _run_attempt_review_grade(attempt_id, data_root=data_root)


def _run_attempt_review_regrade(attempt_id: str, *, data_root: Path, answer_updates: list[str]) -> None:
    try:
        parsed_updates = attempt_review_workflow.parse_answer_updates(answer_updates)
        result = attempt_review_workflow.regrade_attempt(
            attempt_id,
            parsed_updates,
            data_root=data_root,
        )
    except attempt_review_workflow.AttemptReviewError as exc:
        console.print(f"[red]Attempt regrade failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    wrong = ", ".join(str(question_no) for question_no in result.wrong_question_numbers) or "none"
    archived = ", ".join(str(question_no) for question_no in result.archived_question_numbers) or "none"
    console.print(f"Answer key: {result.answer_key_source}")
    console.print(f"Score: {result.score}/{result.total}")
    console.print(f"Wrong questions: {wrong}")
    console.print(f"Archived review questions: {archived}")
    console.print(f"Review directory: {attempt_review_workflow.attempt_reviews_dir(attempt_id, data_root=data_root)}")


@attempt_review_app.command("regrade")
def attempt_review_regrade_command(
    attempt_id: str = typer.Argument(..., metavar="ATTEMPT_ID", help="Attempt ID."),
    answer_updates: list[str] = typer.Option(
        ...,
        "--answer",
        "-a",
        help="Answer correction as QUESTION=CHOICE. Repeat for multiple questions.",
    ),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
) -> None:
    """Update selected answers by question number and recompute review files."""

    _run_attempt_review_regrade(attempt_id, data_root=data_root, answer_updates=answer_updates)


def _run_attempt_review_migrate_self_review(*, data_root: Path) -> None:
    try:
        result = attempt_review_workflow.migrate_self_review_files(data_root=data_root)
    except attempt_review_workflow.AttemptReviewError as exc:
        console.print(f"[red]Self-review migration failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Scanned review files: {result.scanned}")
    console.print(f"Migrated review files: {result.migrated}")


@attempt_review_app.command("migrate-self-review")
def attempt_review_migrate_self_review_command(
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
) -> None:
    """Migrate legacy user self-review fields into the simplified schema."""

    _run_attempt_review_migrate_self_review(data_root=data_root)


def _run_attempt_review_export(attempt_id: str, *, data_root: Path, out_file: Path | None) -> None:
    try:
        path = attempt_review_workflow.export_feedback_bundle(
            attempt_id,
            data_root=data_root,
            out_file=out_file,
        )
    except attempt_review_workflow.AttemptReviewError as exc:
        console.print(f"[red]Feedback export failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Feedback request: {path}")


@attempt_review_app.command("feedback-export")
def attempt_review_feedback_export_command(
    attempt_id: str = typer.Argument(..., metavar="ATTEMPT_ID", help="Attempt ID."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
    out_file: Path | None = typer.Option(None, "--out-file", help="Output feedback request JSON path."),
) -> None:
    """Write a local bundle for assistant feedback."""

    _run_attempt_review_export(attempt_id, data_root=data_root, out_file=out_file)


def _run_attempt_review_import(attempt_id: str, *, data_root: Path, feedback_file: Path) -> None:
    try:
        reviews = attempt_review_workflow.import_assistant_feedback(
            attempt_id,
            feedback_file,
            data_root=data_root,
        )
    except attempt_review_workflow.AttemptReviewError as exc:
        console.print(f"[red]Feedback import failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Imported assistant feedback for {len(reviews)} review(s).")


@attempt_review_app.command("feedback-import")
def attempt_review_feedback_import_command(
    attempt_id: str = typer.Argument(..., metavar="ATTEMPT_ID", help="Attempt ID."),
    feedback_file: Path = typer.Option(..., "--file", exists=True, help="Assistant feedback JSON file."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
) -> None:
    """Import assistant feedback without overwriting user self-review."""

    _run_attempt_review_import(attempt_id, data_root=data_root, feedback_file=feedback_file)


def _run_attempt_review_serve(
    attempt_id: str,
    *,
    data_root: Path,
    host: str,
    port: int,
    no_open: bool,
    unsafe_allow_remote: bool,
) -> None:
    if not _is_loopback_host(host) and not unsafe_allow_remote:
        console.print(
            "[red]Refusing to bind the unauthenticated workbench to a non-loopback host.[/red]\n"
            "Use --unsafe-allow-remote only on a trusted network."
        )
        raise typer.Exit(1)
    try:
        state = attempt_review_workflow.initialize_attempt_reviews(attempt_id, data_root=data_root)
    except attempt_review_workflow.AttemptReviewError as exc:
        console.print(f"[red]Attempt review setup failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Attempt: {attempt_review_workflow.attempt_path(attempt_id, data_root=data_root)}")
    console.print(f"Review directory: {attempt_review_workflow.attempt_reviews_dir(attempt_id, data_root=data_root)}")
    console.print(f"Wrong questions: {len(state.wrong_question_numbers)}")
    url = f"http://{host}:{port}/"
    console.print(f"Starting local attempt-review workbench: {url}")
    console.print("Press Ctrl+C to stop.")
    try:
        attempt_review_workflow.serve_review_workbench(
            attempt_id,
            data_root=data_root,
            host=host,
            port=port,
            open_browser=not no_open,
        )
    except KeyboardInterrupt:
        console.print("\nStopped attempt-review workbench.")
    except OSError as exc:
        console.print(f"[red]Failed to start workbench:[/red] {exc}")
        raise typer.Exit(1) from exc


@attempt_review_app.command("serve")
def attempt_review_serve_command(
    attempt_id: str = typer.Argument(..., metavar="ATTEMPT_ID", help="Attempt ID."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, "--data-root", help="Local data root."),
    host: str = typer.Option("127.0.0.1", "--host", help="Local bind host."),
    port: int = typer.Option(8766, "--port", help="Local bind port."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open the browser automatically."),
    unsafe_allow_remote: bool = typer.Option(
        False,
        "--unsafe-allow-remote",
        help="Allow binding the unauthenticated workbench to a non-loopback host.",
    ),
) -> None:
    """Serve the separate attempt self-review workbench."""

    _run_attempt_review_serve(
        attempt_id,
        data_root=data_root,
        host=host,
        port=port,
        no_open=no_open,
        unsafe_allow_remote=unsafe_allow_remote,
    )


app.add_typer(attempt_review_app, name="attempt-review")


def _run_ocr(
    exam_id: str,
    pages: str,
    *,
    pdf: Path | None,
    data_root: Path,
    out_dir: Path,
    run_id: str | None,
    dpi: int,
    reuse_existing_images: bool,
    no_annotated_blocks: bool,
    ocr_batch_chunk_size: int,
    paddle_device: str | None,
    paddle_text_recognition_batch_size: int | None,
    paddle_text_det_limit_side_len: int | None,
    paddle_preimport_paddle: bool,
) -> None:
    pdf_path = pdf or _default_pdf_path(exam_id, data_root)
    if not pdf_path.exists():
        console.print(
            f"[red]PDF not found:[/red] {pdf_path}\n"
            "Pass --pdf explicitly or place the file at the path shown above."
        )
        raise typer.Exit(1)
    try:
        parsed_pages = ocr_crops.parse_pages(pages)
    except ValueError as exc:
        console.print(f"[red]Invalid PAGES:[/red] {exc}")
        raise typer.Exit(1) from exc

    actual_run_id = run_id or _default_run_id(exam_id, parsed_pages)
    argv = [
        "--pdf",
        str(pdf_path),
        "--pages",
        pages,
        "--out-dir",
        str(out_dir),
        "--run-id",
        actual_run_id,
        "--dpi",
        str(dpi),
        "--ocr-batch-chunk-size",
        str(ocr_batch_chunk_size),
    ]
    if reuse_existing_images:
        argv.append("--reuse-existing-images")
    if no_annotated_blocks:
        argv.append("--no-annotated-blocks")
    if paddle_device:
        argv.extend(["--paddle-device", paddle_device])
    if paddle_text_recognition_batch_size is not None:
        argv.extend(["--paddle-text-recognition-batch-size", str(paddle_text_recognition_batch_size)])
    if paddle_text_det_limit_side_len is not None:
        argv.extend(["--paddle-text-det-limit-side-len", str(paddle_text_det_limit_side_len)])
    if paddle_preimport_paddle:
        argv.append("--paddle-preimport-paddle")

    args = ocr_crops.parse_args(argv)
    run_dir = ocr_crops.make_run_dir(args.out_dir, args.run_id)
    payload = ocr_crops.build_stream(args, run_dir)
    ocr_crops.write_suggestions(run_dir, payload)
    ocr_crops.print_summary(run_dir, payload)
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
    dpi: int = typer.Option(300, "--dpi", min=1, help="PDF render DPI."),
    reuse_existing_images: bool = typer.Option(
        False,
        "--reuse-existing-images",
        help="Reuse rendered page and column PNGs already present in the run directory.",
    ),
    no_annotated_blocks: bool = typer.Option(False, "--no-annotated-blocks", help="Skip annotated page-column images."),
    ocr_batch_chunk_size: int = typer.Option(4, "--ocr-batch-chunk-size", min=1, help="Page-column blocks per OCR batch chunk."),
    paddle_device: str | None = typer.Option(None, "--paddle-device", help="Optional PaddleOCR device, for example cpu or gpu:0."),
    paddle_text_recognition_batch_size: int | None = typer.Option(
        None,
        "--paddle-text-recognition-batch-size",
        help="Optional PaddleOCR text-recognition batch size.",
    ),
    paddle_text_det_limit_side_len: int | None = typer.Option(
        None,
        "--paddle-text-det-limit-side-len",
        min=1,
        help="Optional PaddleOCR text detection max side length.",
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
        dpi=dpi,
        reuse_existing_images=reuse_existing_images,
        no_annotated_blocks=no_annotated_blocks,
        ocr_batch_chunk_size=ocr_batch_chunk_size,
        paddle_device=paddle_device,
        paddle_text_recognition_batch_size=paddle_text_recognition_batch_size,
        paddle_text_det_limit_side_len=paddle_text_det_limit_side_len,
        paddle_preimport_paddle=paddle_preimport_paddle,
    )


@app.command("ocr-benchmark-summary")
def ocr_benchmark_summary_command(
    baseline: Path = typer.Argument(..., exists=True, help="Baseline suggestions.json path."),
    candidate: list[Path] = typer.Option(
        [],
        "--candidate",
        exists=True,
        help="Candidate suggestions.json path. Repeat for multiple candidates.",
    ),
    baseline_kind: str = typer.Option("cold", "--baseline-kind", help="Run kind label for the baseline, for example cold or warm."),
    candidate_kind: str = typer.Option("warm", "--candidate-kind", help="Run kind label for candidates, for example warm."),
    out_dir: Path = typer.Option(
        Path("artifacts/ocr_benchmarks"),
        "--out-dir",
        help="Directory where summary.json and summary.csv are written.",
    ),
) -> None:
    """Summarize OCR benchmark results from suggestion artifacts."""

    try:
        baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
        records = [benchmark_record(name=baseline.parent.name, run_kind=baseline_kind, payload=baseline_payload)]
        for path in candidate:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(
                benchmark_record(
                    name=path.parent.name,
                    run_kind=candidate_kind,
                    payload=payload,
                    baseline_payload=baseline_payload,
                )
            )
        json_path, csv_path = write_benchmark_summary(records, out_dir)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        console.print(f"[red]OCR benchmark summary failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Benchmark summary: {json_path}")
    console.print(f"Benchmark CSV: {csv_path}")


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
    enable_spacing_cleanup: bool = True,
    enable_morphology_checks: bool = True,
    local_nlp_workers: int | None = None,
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
            local_nlp_workers=local_nlp_workers,
            progress=console.print,
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
        True,
        "--enable-spacing-cleanup/--no-spacing-cleanup",
        help="Apply local Korean spacing cleanup to OCR drafts when a backend is installed.",
    ),
    enable_morphology_checks: bool = typer.Option(
        True,
        "--enable-morphology-checks/--no-morphology-checks",
        help="Run Kiwi/kiwipiepy morphology checks for OCR draft warnings when installed.",
    ),
    local_nlp_workers: int | None = typer.Option(
        None,
        "--local-nlp-workers",
        min=1,
        help="Worker count for optional Kiwi morphology checks. Defaults to min(os.cpu_count(), 4).",
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
        local_nlp_workers=local_nlp_workers,
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
        True,
        "--enable-spacing-cleanup/--no-spacing-cleanup",
        help="Apply local Korean spacing cleanup to OCR drafts when a backend is installed.",
    ),
    enable_morphology_checks: bool = typer.Option(
        True,
        "--enable-morphology-checks/--no-morphology-checks",
        help="Run Kiwi/kiwipiepy morphology checks for OCR draft warnings when installed.",
    ),
    local_nlp_workers: int | None = typer.Option(
        None,
        "--local-nlp-workers",
        min=1,
        help="Worker count for optional Kiwi morphology checks. Defaults to min(os.cpu_count(), 4).",
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
        local_nlp_workers=local_nlp_workers,
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
