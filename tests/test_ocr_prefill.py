from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from leet_practice import verification
from leet_practice.verification import CandidateType, DraftOptions, generate_ocr_draft, initialize_review_state, reapply_ocr_draft, update_candidate


def write_suggestion_run(tmp_path: Path, *, passage_text: str = "passage line", question_text: str) -> Path:
    run_dir = tmp_path / "artifacts" / "question_crop_suggestions" / "run"
    (run_dir / "q01_candidate").mkdir(parents=True)
    (run_dir / "set_01_03_passage_candidate").mkdir(parents=True)
    (run_dir / "q01_candidate" / "q01_candidate_preview.png").write_bytes(b"preview")
    (run_dir / "set_01_03_passage_candidate" / "set_01_03_passage_candidate_preview.png").write_bytes(b"preview")
    passage_lines = passage_text.splitlines()
    question_lines = question_text.splitlines()
    rows = [{"row_index": index, "text": text} for index, text in enumerate(passage_lines + question_lines)]
    (run_dir / "page_001_left.paddleocr.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    payload = {
        "artifact_type": "candidate_question_crop_suggestions",
        "suggestions": [
            {
                "suggestion_id": "set_01_03_passage",
                "kind": "candidate_passage_crop_suggestion",
                "start_question": 1,
                "end_question": 3,
                "candidate_preview_path": "set_01_03_passage_candidate/set_01_03_passage_candidate_preview.png",
                "parts": [
                    {
                        "page": 1,
                        "column": "left",
                        "block_id": "p001_left",
                        "included_row_ids": [f"p001_left_r{index:03d}" for index in range(len(passage_lines))],
                    }
                ],
            },
            {
                "suggestion_id": "q01",
                "kind": "candidate_question_crop_suggestion",
                "question_number": 1,
                "set_start_question": 1,
                "set_end_question": 3,
                "candidate_preview_path": "q01_candidate/q01_candidate_preview.png",
                "parts": [
                    {
                        "page": 1,
                        "column": "left",
                        "block_id": "p001_left",
                        "included_row_ids": [
                            f"p001_left_r{index:03d}"
                            for index in range(len(passage_lines), len(passage_lines) + len(question_lines))
                        ],
                    }
                ],
            },
        ],
    }
    suggestions_path = run_dir / "suggestions.json"
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")
    return suggestions_path


def test_passage_prefill_uses_raw_ocr_body(tmp_path: Path) -> None:
    suggestions_path = write_suggestion_run(tmp_path, passage_text="첫 줄\n둘째 줄", question_text="문 1. 질문")

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")

    passage = state.candidates[0]
    assert passage.raw_ocr_text == "첫 줄\n둘째 줄"
    assert passage.verified_text == "첫 줄 둘째 줄"
    assert passage.ocr_draft_text == "첫 줄\n둘째 줄"
    assert passage.prefill_source == "ocr_heuristic"
    assert "joined_forced_line_breaks" in passage.correction_steps


def test_passage_prefill_separates_standard_header_from_body() -> None:
    raw = "[1~3] 다음 글을 읽고 물음에 답하시오.\n문학이 사회를 반영한다.\n법의 영역에도 적용된다."

    draft = generate_ocr_draft(CandidateType.PASSAGE, raw)

    assert draft.verified_text == "[1~3] 다음 글을 읽고 물음에 답하시오.\n\n문학이 사회를 반영한다. 법의 영역에도 적용된다."
    assert "formatted_passage_header_break" in draft.correction_steps


def test_passage_prefill_separates_header_even_without_question_range() -> None:
    raw = "다음 글을 읽고 물음에 답하시오.\n첫 문장\n둘째 문장"

    draft = generate_ocr_draft(CandidateType.PASSAGE, raw)

    assert draft.verified_text == "다음 글을 읽고 물음에 답하시오.\n\n첫 문장 둘째 문장"
    assert "formatted_passage_header_break" in draft.correction_steps


def test_question_prefill_splits_circled_choice_markers() -> None:
    raw = "\ubb38 1. 다음 중 옳은 것은?\n\u2460 갑\n\u2461 을\n\u2462 병\n\u2463 정\n\u2464 무"

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=1)

    assert draft.stem == "다음 중 옳은 것은?"
    assert draft.choices == ["갑", "을", "병", "정", "무"]
    assert "removed_leading_question_marker" in draft.correction_steps
    assert not draft.warnings


def test_question_prefill_splits_numeric_and_multiline_choices() -> None:
    raw = "1. 사례에 대한 설명으로 옳은 것은?\n1) 첫째 줄\n계속 설명\n2) 둘째\n3) 셋째\n4) 넷째\n5) 다섯째"

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=1)

    assert draft.stem == "사례에 대한 설명으로 옳은 것은?"
    assert draft.choices[0] == "첫째 줄 계속 설명"
    assert draft.choices[4] == "다섯째"
    assert not draft.warnings


def test_question_prefill_normalizes_punctuation_spacing_without_changing_numbers() -> None:
    raw = (
        "1. \uc801\uc808\ud55c \uac83\uc740?\n"
        "1. \uc800\ucd95\ub7c9,\uac10\uac00\uc0c1\uac01\ub7c9,\ud22c\uc790\ub7c9\uc774 \ubaa8\ub450 \ubcc0\ud55c\ub2e4.\ub530\ub77c\uc11c \uc120\ud0dd\ud55c\ub2e4.\n"
        "2. 1,000\uc6d0\uc774\ub2e4.\n"
        "3. 3.14\ubcf4\ub2e4 \ud06c\ub2e4.\n"
        "4. \ub137\uc9f8\n"
        "5. \ub2e4\uc12f\uc9f8"
    )

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=1)

    assert draft.choices[0] == "\uc800\ucd95\ub7c9, \uac10\uac00\uc0c1\uac01\ub7c9, \ud22c\uc790\ub7c9\uc774 \ubaa8\ub450 \ubcc0\ud55c\ub2e4. \ub530\ub77c\uc11c \uc120\ud0dd\ud55c\ub2e4."
    assert draft.choices[1] == "1,000\uc6d0\uc774\ub2e4."
    assert draft.choices[2] == "3.14\ubcf4\ub2e4 \ud06c\ub2e4."
    assert "normalized_punctuation_spacing" in draft.correction_steps


def test_question_number_five_is_not_treated_as_choice_five() -> None:
    raw = "5. 다음 글에 대한 설명으로 옳은 것은?\n1. 첫째\n2. 둘째\n3. 셋째\n4. 넷째\n5. 다섯째"

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=5)

    assert draft.stem == "다음 글에 대한 설명으로 옳은 것은?"
    assert draft.choices == ["첫째", "둘째", "셋째", "넷째", "다섯째"]
    assert "ignored_out_of_sequence_choice_markers:5" not in draft.warnings


def test_question_prefill_splits_mixed_circled_and_bare_numeric_choice_markers() -> None:
    raw = (
        "5.\uc5d0 \ub300\ud574 \ucd94\ub860\ud55c \uac83\uc73c\ub85c \uc801\uc808\ud55c \uac83\uc740?\n"
        "\u2460\uac19\uc740 \uc785\ub825\uac12\uc73c\ub85c \uc5ec\ub7ec \uaddc\uce59\uc774 \ub3d9\uc2dc\uc5d0 \ub9cc\uc871\ub420 \uc218 \uc788\ub2e4.\n"
        "\uc815\ucc45\uc744 \uae30\ubcf8\uac12\uc73c\ub85c \uc124\uc815\ud560 \uc218 \uc5c6\ub2e4.\n"
        "2 \uc758\uc0ac\uacb0\uc815 \ud14c\uc774\ube14\uc758 \uc785\ub825\uc774 \uc5ec\ub7ec \uac1c\uc77c \uacbd\uc6b0\n"
        "\uc5b4\ub290 \ud558\ub098\uac00 \ucc38\uc774\uba74 \uadf8 \uaddc\uce59\uc740 \ub9cc\uc871\ub41c\ub2e4.\n"
        "3 \uc5b4\ub5a4 \uc758\uc0ac\uacb0\uc815 \ub85c\uc9c1\uc758 \uc785\ub825\uc73c\ub85c \uc0ac\uc6a9\ub41c\ub2e4.\n"
        "4\ucd5c\uc0c1\uc704\uc758 \uc758\uc0ac\uacb0\uc815 \ub178\ub4dc\uc5d0 \uc9c1\uc811 \uc5f0\uacb0\ub418\uc9c0 \uc54a\uc558\ub2e4.\n"
        "5\uc758\uc0ac\uacb0\uc815 \ub178\ub4dc\uac00 \uc5ec\ub7ec \uacc4\uce35\uc73c\ub85c \uad6c\uc131\ub420 \uacbd\uc6b0."
    )

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=5)

    assert draft.stem == "\uc5d0 \ub300\ud574 \ucd94\ub860\ud55c \uac83\uc73c\ub85c \uc801\uc808\ud55c \uac83\uc740?"
    assert draft.choices[0].startswith("\uac19\uc740 \uc785\ub825\uac12\uc73c\ub85c")
    assert draft.choices[0].endswith("\uc124\uc815\ud560 \uc218 \uc5c6\ub2e4.")
    assert draft.choices[1].startswith("\uc758\uc0ac\uacb0\uc815 \ud14c\uc774\ube14\uc758")
    assert draft.choices[2].startswith("\uc5b4\ub5a4 \uc758\uc0ac\uacb0\uc815")
    assert draft.choices[3].startswith("\ucd5c\uc0c1\uc704\uc758 \uc758\uc0ac\uacb0\uc815")
    assert draft.choices[4].startswith("\uc758\uc0ac\uacb0\uc815 \ub178\ub4dc\uac00")
    assert not draft.warnings


def test_out_of_sequence_numeric_marker_stays_in_stem_before_choices_start() -> None:
    raw = "5. 문제 번호가 먼저 보이는 줄\n조건을 읽고 답하시오\n1. 첫째\n2. 둘째\n3. 셋째\n4. 넷째\n5. 다섯째"

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=None)

    assert draft.stem == "5. 문제 번호가 먼저 보이는 줄 조건을 읽고 답하시오"
    assert draft.choices == ["첫째", "둘째", "셋째", "넷째", "다섯째"]
    assert "ignored_out_of_sequence_choice_markers:5" in draft.warnings


def test_question_prefill_records_incomplete_choice_warning() -> None:
    raw = "문 1. 고르시오\n1. 하나\n2. 둘\n3. 셋\n4. 넷"

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=1)

    assert draft.choices[:4] == ["하나", "둘", "셋", "넷"]
    assert draft.choices[4] == ""
    assert "choices_detected_4" in draft.warnings


def test_existing_user_edits_survive_normal_reload_and_explicit_reapply_overwrites(tmp_path: Path) -> None:
    suggestions_path = write_suggestion_run(
        tmp_path,
        question_text="문 1. 질문\n1) 하나\n2) 둘\n3) 셋\n4) 넷\n5) 다섯",
    )
    data_root = tmp_path / "data"
    initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)
    update_candidate("leet-2026-verbal-even", "q01", {"stem": "사용자 수정"}, data_root=data_root)

    reloaded = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)
    question = next(candidate for candidate in reloaded.candidates if candidate.candidate_id == "q01")
    assert question.stem == "사용자 수정"

    reapplied = reapply_ocr_draft("leet-2026-verbal-even", "q01", data_root=data_root)
    assert reapplied.stem == "질문"


def test_missing_optional_backends_record_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_backend(name: str):
        raise ImportError(name)

    monkeypatch.setattr(verification, "import_module", missing_backend)

    draft = generate_ocr_draft(
        CandidateType.PASSAGE,
        "붙여쓰기문장",
        options=DraftOptions(enable_spacing_cleanup=True, enable_morphology_checks=True),
    )

    assert draft.verified_text == "붙여쓰기문장"
    assert "spacing_backend_unavailable" in draft.warnings
    assert "kiwi_backend_unavailable" in draft.warnings


def test_fake_spacing_and_kiwi_backends_record_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSpacing:
        def __call__(self, text: str) -> str:
            return text.replace("붙여쓰기문장", "붙여쓰기 문장")

    class FakeKiwi:
        def tokenize(self, text: str) -> list[object]:
            return [object(), object()]

    def fake_import(name: str):
        if name == "pykospacing":
            return SimpleNamespace(Spacing=FakeSpacing)
        if name == "kiwipiepy":
            return SimpleNamespace(Kiwi=lambda: FakeKiwi())
        raise ImportError(name)

    monkeypatch.setattr(verification, "import_module", fake_import)

    draft = generate_ocr_draft(
        CandidateType.PASSAGE,
        "붙여쓰기문장",
        options=DraftOptions(enable_spacing_cleanup=True, enable_morphology_checks=True),
    )

    assert draft.verified_text == "붙여쓰기 문장"
    assert "spacing_cleanup:pykospacing" in draft.correction_steps
    assert "kiwi_morphology_checked" in draft.correction_steps
