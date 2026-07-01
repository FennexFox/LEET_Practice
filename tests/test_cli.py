from __future__ import annotations

import shutil
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


def test_verify_uses_latest_default_suggestions(
    tmp_path: Path,
    suggestion_run: Path,
    monkeypatch,
) -> None:
    default_run = tmp_path / "artifacts" / "question_crop_suggestions" / "leet-2026-verbal-even-p001-001"
    shutil.copytree(suggestion_run.parent, default_run)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "verify",
            "leet-2026-verbal-even",
            "--data-root",
            str(tmp_path / "data"),
            "--init-only",
        ],
    )

    assert result.exit_code == 0
    assert "Suggestions:" in result.output
    assert "leet-2026-verbal-even-p001-001" in result.output


def test_promote_accepts_positional_exam_id(tmp_path: Path, suggestion_run: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "promote",
            "leet-2026-verbal-even",
            "--data-root",
            str(tmp_path / "data"),
        ],
    )

    assert result.exit_code == 0
    assert "Promoted" in result.output


def test_ocr_defaults_pdf_path_from_exam_id(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "ocr",
            "leet-2026-verbal-even",
            "1-2",
            "--data-root",
            str(tmp_path / "data"),
        ],
    )

    assert result.exit_code == 1
    assert "PDF not found" in result.output
    assert "raw_pdfs" in result.output
    assert "leet-2026-verbal-even" in result.output
    assert "leet-2026-verbal-even.pdf" in result.output
