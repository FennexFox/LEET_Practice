from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from leet_practice.cli import app


def test_review_crops_rejects_non_loopback_host_without_unsafe_opt_in(tmp_path, suggestion_run: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "review-crops",
            "--exam-id",
            "leet-2026-verbal-even",
            "--suggestions",
            str(suggestion_run),
            "--data-root",
            str(tmp_path / "data"),
            "--host",
            "0.0.0.0",
            "--no-open",
        ],
    )

    assert result.exit_code == 1
    assert "Refusing to bind" in result.output


def test_review_crops_rejects_overwrite_with_refresh_preserving_edits(tmp_path, suggestion_run: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "review-crops",
            "--exam-id",
            "leet-2026-verbal-even",
            "--suggestions",
            str(suggestion_run),
            "--data-root",
            str(tmp_path / "data"),
            "--overwrite",
            "--refresh-preserving-edits",
            "--init-only",
        ],
    )

    assert result.exit_code == 1
    assert "--overwrite and --refresh-preserving-edits cannot be combined" in result.output
