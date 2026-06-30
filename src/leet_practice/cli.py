"""Command line entrypoint for LEET Practice."""

from __future__ import annotations

from pathlib import Path

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


@app.command()
def review_crops(
    exam_id: str = typer.Option(..., "--exam-id", help="Exam ID for the verification workspace."),
    suggestions: Path = typer.Option(..., "--suggestions", exists=True, help="Path to suggestions.json."),
    data_root: Path = typer.Option(Path("data"), "--data-root", help="Local data root."),
    host: str = typer.Option("127.0.0.1", "--host", help="Local bind host."),
    port: int = typer.Option(8765, "--port", help="Local bind port."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open the browser automatically."),
    init_only: bool = typer.Option(False, "--init-only", help="Initialize review state without starting the server."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Rebuild review state from suggestions.json."),
) -> None:
    """Review OCR crop suggestions in a local browser workbench."""

    try:
        state = initialize_review_state(
            exam_id,
            suggestions,
            data_root=data_root,
            overwrite=overwrite,
        )
    except VerificationError as exc:
        console.print(f"[red]Verification setup failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    state_path = review_state_path(exam_id, data_root=data_root)
    console.print(f"Review state: {state_path}")
    console.print(f"Candidates: {len(state.candidates)}")
    if init_only:
        return

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


@app.command()
def promote_verified(
    exam_id: str = typer.Option(..., "--exam-id", help="Exam ID to promote."),
    data_root: Path = typer.Option(Path("data"), "--data-root", help="Local data root."),
) -> None:
    """Promote accepted verification drafts into canonical JSONL files."""

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
