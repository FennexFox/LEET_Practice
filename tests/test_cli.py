from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from leet_practice import cli

app = cli.app


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


def test_verify_default_suggestions_does_not_match_exam_id_prefix(
    tmp_path: Path,
    suggestion_run: Path,
    monkeypatch,
) -> None:
    artifacts_root = tmp_path / "artifacts" / "question_crop_suggestions"
    exact_run = artifacts_root / "leet-2026-verbal"
    prefix_run = artifacts_root / "leet-2026-verbal-even-p001-001"
    shutil.copytree(suggestion_run.parent, exact_run)
    shutil.copytree(suggestion_run.parent, prefix_run)
    (prefix_run / "suggestions.json").touch()
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "verify",
            "leet-2026-verbal",
            "--data-root",
            str(tmp_path / "data"),
            "--init-only",
        ],
    )

    assert result.exit_code == 0
    assert "Suggestions:" in result.output
    assert "leet-2026-verbal-even-p001-001" not in result.output


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


def test_ocr_invalid_pages_fails_before_creating_run_dir(tmp_path: Path) -> None:
    pdf_path = tmp_path / "data" / "raw_pdfs" / "leet-2026-verbal-even.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"not a real pdf")
    out_dir = tmp_path / "artifacts"

    result = CliRunner().invoke(
        app,
        [
            "ocr",
            "leet-2026-verbal-even",
            "0",
            "--data-root",
            str(tmp_path / "data"),
            "--out-dir",
            str(out_dir),
            "--run-id",
            "should-not-exist",
        ],
    )

    assert result.exit_code == 1
    assert "Invalid PAGES" in result.output
    assert not (out_dir / "should-not-exist").exists()


def test_verify_enables_local_nlp_cleanup_by_default(tmp_path: Path, suggestion_run: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_initialize_review_state(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(candidates=[])

    monkeypatch.setattr(cli, "initialize_review_state", fake_initialize_review_state)

    result = CliRunner().invoke(
        app,
        [
            "verify",
            "leet-2026-verbal-even",
            "--suggestions",
            str(suggestion_run),
            "--data-root",
            str(tmp_path / "data"),
            "--init-only",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["enable_spacing_cleanup"] is True
    assert captured["kwargs"]["enable_morphology_checks"] is True


def test_verify_can_disable_default_local_nlp_cleanup(tmp_path: Path, suggestion_run: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_initialize_review_state(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(candidates=[])

    monkeypatch.setattr(cli, "initialize_review_state", fake_initialize_review_state)

    result = CliRunner().invoke(
        app,
        [
            "verify",
            "leet-2026-verbal-even",
            "--suggestions",
            str(suggestion_run),
            "--data-root",
            str(tmp_path / "data"),
            "--no-spacing-cleanup",
            "--no-morphology-checks",
            "--init-only",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["enable_spacing_cleanup"] is False
    assert captured["kwargs"]["enable_morphology_checks"] is False


def test_review_crops_enables_local_nlp_cleanup_by_default(tmp_path: Path, suggestion_run: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_initialize_review_state(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(candidates=[])

    monkeypatch.setattr(cli, "initialize_review_state", fake_initialize_review_state)

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
            "--init-only",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["enable_spacing_cleanup"] is True
    assert captured["kwargs"]["enable_morphology_checks"] is True


def test_verify_forwards_local_nlp_workers(tmp_path: Path, suggestion_run: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_initialize_review_state(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(candidates=[])

    monkeypatch.setattr(cli, "initialize_review_state", fake_initialize_review_state)

    result = CliRunner().invoke(
        app,
        [
            "verify",
            "leet-2026-verbal-even",
            "--suggestions",
            str(suggestion_run),
            "--data-root",
            str(tmp_path / "data"),
            "--enable-morphology-checks",
            "--local-nlp-workers",
            "7",
            "--init-only",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["enable_morphology_checks"] is True
    assert captured["kwargs"]["local_nlp_workers"] == 7


def test_review_crops_forwards_local_nlp_workers(tmp_path: Path, suggestion_run: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_initialize_review_state(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(candidates=[])

    monkeypatch.setattr(cli, "initialize_review_state", fake_initialize_review_state)

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
            "--enable-morphology-checks",
            "--local-nlp-workers",
            "6",
            "--init-only",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["enable_morphology_checks"] is True
    assert captured["kwargs"]["local_nlp_workers"] == 6
