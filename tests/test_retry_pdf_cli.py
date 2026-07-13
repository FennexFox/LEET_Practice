from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from leet_practice import cli


def test_retry_pdf_help_lists_selection_and_output_options() -> None:
    result = CliRunner().invoke(cli.app, ["retry-pdf", "--help"])

    assert result.exit_code == 0
    for option in (
        "--limit",
        "--tag",
        "--year",
        "--section",
        "--include-holdout",
        "--include-completed",
        "--review-file",
        "--title",
        "--output",
        "--font",
        "--data-root",
    ):
        assert option in result.output


def test_retry_pdf_forwards_filters_manual_selection_and_paths(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    pdf_path = tmp_path / "out" / "retry.pdf"
    manifest_path = pdf_path.with_suffix(".json")
    data_root = tmp_path / "data"
    font_path = tmp_path / "fonts" / "korean.ttf"
    review_a = tmp_path / "reviews" / "a.json"
    review_b = tmp_path / "reviews" / "b.json"

    def fake_create_retry_pdf_bundle(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(session_id="retry-test", pdf_path=pdf_path, manifest_path=manifest_path)

    monkeypatch.setattr(cli.retry_pdf_workflow, "create_retry_pdf_bundle", fake_create_retry_pdf_bundle)

    result = CliRunner().invoke(
        cli.app,
        [
            "retry-pdf",
            "--limit",
            "12",
            "--tag",
            "FORMAL_CONDITION_ERROR",
            "--tag",
            "CHOICE_VERIFICATION_FAILURE",
            "--year",
            "2024",
            "--year",
            "2025",
            "--section",
            "언어이해",
            "--section",
            "추리논증",
            "--include-holdout",
            "--include-completed",
            "--review-file",
            str(review_a),
            "--review-file",
            str(review_b),
            "--title",
            "집중력 재점검",
            "--output",
            str(pdf_path),
            "--font",
            str(font_path),
            "--data-root",
            str(data_root),
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "data_root": data_root,
        "review_files": [review_a, review_b],
        "limit": 12,
        "tags": ["FORMAL_CONDITION_ERROR", "CHOICE_VERIFICATION_FAILURE"],
        "years": [2024, 2025],
        "sections": ["언어이해", "추리논증"],
        "include_holdout": True,
        "include_completed": True,
        "title": "집중력 재점검",
        "output_path": pdf_path,
        "font_path": font_path,
    }
    assert "PDF:" in result.output
    assert "Session: retry-test" in result.output
    assert "retry.pdf" in result.output
    assert "Manifest:" in result.output
    assert "retry.json" in result.output


def test_retry_pdf_uses_documented_defaults(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    pdf_path = tmp_path / "retry.pdf"

    def fake_create_retry_pdf_bundle(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            session_id="retry-default",
            pdf_path=pdf_path,
            manifest_path=pdf_path.with_suffix(".json"),
        )

    monkeypatch.setattr(cli.retry_pdf_workflow, "create_retry_pdf_bundle", fake_create_retry_pdf_bundle)

    result = CliRunner().invoke(cli.app, ["retry-pdf"])

    assert result.exit_code == 0
    assert captured == {
        "data_root": Path("data"),
        "review_files": [],
        "limit": 20,
        "tags": [],
        "years": [],
        "sections": [],
        "include_holdout": False,
        "include_completed": False,
        "title": "LEET 오답 재풀이",
        "output_path": None,
        "font_path": None,
    }


def test_retry_pdf_reports_generation_errors_without_traceback(monkeypatch) -> None:
    def fail_create_retry_pdf_bundle(**_kwargs):
        raise cli.retry_pdf_workflow.RetryPdfError("선택 가능한 오답 문항이 없습니다.")

    monkeypatch.setattr(cli.retry_pdf_workflow, "create_retry_pdf_bundle", fail_create_retry_pdf_bundle)

    result = CliRunner().invoke(cli.app, ["retry-pdf"])

    assert result.exit_code == 1
    assert "Retry PDF generation failed" in result.output
    assert "선택 가능한 오답 문항이 없습니다." in result.output
    assert "Traceback" not in result.output


def test_retry_pdf_rejects_non_positive_limit_before_generation(monkeypatch) -> None:
    called = False

    def fake_create_retry_pdf_bundle(**_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(cli.retry_pdf_workflow, "create_retry_pdf_bundle", fake_create_retry_pdf_bundle)

    result = CliRunner().invoke(cli.app, ["retry-pdf", "--limit", "0"])

    assert result.exit_code == 2
    assert not called
