"""Command line entrypoint for LEET Practice."""

from __future__ import annotations

import typer
from rich.console import Console

from leet_practice import __version__

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
    console.print("- data/canonical/: verified local exam data")
    console.print("- data/attempts/: personal attempt records")
    console.print("- data/reviews/: wrong-answer reviews")
