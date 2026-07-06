from __future__ import annotations

import json
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


def test_attempt_review_serve_rejects_non_loopback_host_without_unsafe_opt_in(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "attempt-review",
            "serve",
            "attempt-001",
            "--data-root",
            str(tmp_path / "data"),
            "--host",
            "0.0.0.0",
            "--no-open",
        ],
    )

    assert result.exit_code == 1
    assert "Refusing to bind" in result.output


def test_attempt_review_create_and_grade(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    canonical_dir = data_root / "canonical" / exam_id
    canonical_dir.mkdir(parents=True)
    (canonical_dir / "answer_key.json").write_text(json.dumps({"answers": {"1": 1, "2": 4}}), encoding="utf-8")

    create_result = CliRunner().invoke(
        app,
        [
            "attempt-review",
            "create",
            "attempt-001",
            exam_id,
            "--answers",
            "12",
            "--data-root",
            str(data_root),
        ],
    )
    grade_result = CliRunner().invoke(
        app,
        [
            "attempt-review",
            "grade",
            "attempt-001",
            "--data-root",
            str(data_root),
        ],
    )

    assert create_result.exit_code == 0
    assert (data_root / "attempts" / "attempt-001.json").exists()
    assert grade_result.exit_code == 0
    assert "Score: 1/2" in grade_result.output
    assert (data_root / "reviews" / "attempt-001" / "q02.review.json").exists()


def test_attempt_review_regrade_updates_answer_pairs(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    canonical_dir = data_root / "canonical" / exam_id
    canonical_dir.mkdir(parents=True)
    (canonical_dir / "answer_key.json").write_text(json.dumps({"answers": {"1": 1, "2": 4}}), encoding="utf-8")

    create_result = CliRunner().invoke(
        app,
        [
            "attempt-review",
            "create",
            "attempt-001",
            exam_id,
            "--answers",
            "12",
            "--data-root",
            str(data_root),
        ],
    )
    grade_result = CliRunner().invoke(
        app,
        [
            "attempt-review",
            "grade",
            "attempt-001",
            "--data-root",
            str(data_root),
        ],
    )
    regrade_result = CliRunner().invoke(
        app,
        [
            "attempt-review",
            "regrade",
            "attempt-001",
            "--answer",
            "2=4",
            "--data-root",
            str(data_root),
        ],
    )

    assert create_result.exit_code == 0
    assert grade_result.exit_code == 0
    assert regrade_result.exit_code == 0
    assert "Score: 2/2" in regrade_result.output
    assert "Archived review questions: 2" in regrade_result.output
    assert not (data_root / "reviews" / "attempt-001" / "q02.review.json").exists()
    assert (data_root / "reviews" / "attempt-001" / "archived" / "q02.review.json").exists()


def test_attempt_review_migrate_self_review_command(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    review_dir = data_root / "reviews" / "attempt-001"
    review_dir.mkdir(parents=True)
    review_path = review_dir / "q01.review.json"
    review_path.write_text(
        json.dumps(
            {
                "attempt_id": "attempt-001",
                "exam_id": "leet-2026-reasoning-even",
                "question_no": 1,
                "status": "user_entered",
                "grading": {"selected_choice": 1, "correct_choice": 3, "is_correct": False},
                "user_self_review": {
                    "reasoning_text": "Old reasoning.",
                    "why_selected": "Old why.",
                    "current_reflection": "Old reflection.",
                    "created_by": "user",
                },
                "user_resolution": {"status": "pending", "created_by": "user"},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "attempt-review",
            "migrate-self-review",
            "--data-root",
            str(data_root),
        ],
    )

    assert result.exit_code == 0
    assert "Migrated review files: 1" in result.output
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    assert "[당시 풀이 사고]\nOld reasoning." in payload["user_self_review"]["reasoning_text"]
    assert "[선택 이유]\nOld why." in payload["user_self_review"]["reasoning_text"]
    assert payload["user_self_review"]["current_reflection"] == "Old reflection."
    assert payload["user_self_review"]["memory_confidence"] == "partial"
    assert "why_selected" not in payload["user_self_review"]


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


def test_ocr_forwards_optimization_options(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "data" / "raw_pdfs" / "leet-2026-verbal-even.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF")
    captured: dict[str, object] = {}

    def fake_build_stream(args, run_dir):
        captured["args"] = args
        captured["run_dir"] = run_dir
        return {
            "interrupted": False,
            "processed_pages": [],
            "blocks": [],
            "rows": [],
            "set_header_candidates": [],
            "selected_set_headers": [],
            "anchor_candidates": [],
            "selected_anchors": [],
            "suggestions": [],
            "ocr_errors": [],
        }

    monkeypatch.setattr(cli.ocr_crops, "build_stream", fake_build_stream)
    monkeypatch.setattr(cli.ocr_crops, "write_suggestions", lambda *_: None)
    monkeypatch.setattr(cli.ocr_crops, "print_summary", lambda *_: None)

    result = CliRunner().invoke(
        app,
        [
            "ocr",
            "leet-2026-verbal-even",
            "1",
            "--data-root",
            str(tmp_path / "data"),
            "--dpi",
            "240",
            "--reuse-existing-images",
            "--no-annotated-blocks",
            "--ocr-batch-chunk-size",
            "8",
            "--paddle-text-recognition-batch-size",
            "64",
            "--paddle-text-det-limit-side-len",
            "3584",
        ],
    )

    assert result.exit_code == 0
    args = captured["args"]
    assert args.dpi == 240
    assert args.reuse_existing_images is True
    assert args.no_annotated_blocks is True
    assert args.ocr_batch_chunk_size == 8
    assert args.paddle_text_recognition_batch_size == 64
    assert args.paddle_text_det_limit_side_len == 3584


def test_ocr_benchmark_summary_writes_summary_files(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline" / "suggestions.json"
    candidate = tmp_path / "candidate" / "suggestions.json"
    for path in (baseline, candidate):
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"processed_pages":[1],"ocr_errors":[],"rows":[{"page":1,"text":"1. A"}],'
            '"selected_anchors":[{"question_number":1,"text":"1. A","page":1,"column":"left","stream_y_start":1}],'
            '"suggestions":[{}],"timings":{"ocr_seconds":1,"total_seconds":2},"options":{}}',
            encoding="utf-8",
        )
    out_dir = tmp_path / "summary"

    result = CliRunner().invoke(
        app,
        [
            "ocr-benchmark-summary",
            str(baseline),
            "--candidate",
            str(candidate),
            "--baseline-kind",
            "cold",
            "--candidate-kind",
            "warm",
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.csv").exists()
    payload = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert [record["run_kind"] for record in payload["records"]] == ["cold", "warm"]


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
