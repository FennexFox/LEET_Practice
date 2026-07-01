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


def test_passage_prefill_preserves_blank_ocr_rows_from_suggestions(tmp_path: Path) -> None:
    suggestions_path = write_suggestion_run(
        tmp_path,
        passage_text="Alpha line one\nAlpha line two\n\nBeta line one\nBeta line two",
        question_text="Question 1",
    )

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")

    passage = state.candidates[0]
    assert passage.raw_ocr_text == "Alpha line one\nAlpha line two\n\nBeta line one\nBeta line two"
    assert passage.verified_text == "Alpha line one Alpha line two\n\nBeta line one Beta line two"


def test_passage_prefill_preserves_indented_paragraph_starts_from_ocr_rows(tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "question_crop_suggestions" / "run"
    (run_dir / "set_01_03_passage_candidate").mkdir(parents=True)
    (run_dir / "q01_candidate").mkdir(parents=True)
    (run_dir / "set_01_03_passage_candidate" / "set_01_03_passage_candidate_preview.png").write_bytes(b"preview")
    (run_dir / "q01_candidate" / "q01_candidate_preview.png").write_bytes(b"preview")
    rows = [
        {"row_index": 0, "text": "Header", "local_bbox": [100, 10, 900, 40]},
        {"row_index": 1, "text": "First paragraph line one", "local_bbox": [140, 60, 900, 90]},
        {"row_index": 2, "text": "First paragraph line two", "local_bbox": [100, 110, 900, 140]},
        {"row_index": 3, "text": "Second paragraph line one", "local_bbox": [140, 160, 900, 190]},
        {"row_index": 4, "text": "Second paragraph line two", "local_bbox": [100, 210, 900, 240]},
        {"row_index": 5, "text": "Question 1", "local_bbox": [100, 260, 900, 290]},
    ]
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
                        "included_row_ids": [f"p001_left_r{index:03d}" for index in range(5)],
                    }
                ],
            },
            {
                "suggestion_id": "q01",
                "kind": "candidate_question_crop_suggestion",
                "question_number": 1,
                "candidate_preview_path": "q01_candidate/q01_candidate_preview.png",
                "parts": [
                    {
                        "page": 1,
                        "column": "left",
                        "block_id": "p001_left",
                        "included_row_ids": ["p001_left_r005"],
                    }
                ],
            },
        ],
    }
    suggestions_path = run_dir / "suggestions.json"
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")

    passage = state.candidates[0]
    assert passage.raw_ocr_text == (
        "Header\n\nFirst paragraph line one\nFirst paragraph line two\n\n"
        "Second paragraph line one\nSecond paragraph line two"
    )
    assert passage.verified_text == (
        "Header\n\nFirst paragraph line one First paragraph line two\n\n"
        "Second paragraph line one Second paragraph line two"
    )


def test_passage_prefill_excludes_included_edge_header_fragments(tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "question_crop_suggestions" / "run"
    (run_dir / "set_01_03_passage_candidate").mkdir(parents=True)
    (run_dir / "set_01_03_passage_candidate" / "set_01_03_passage_candidate_preview.png").write_bytes(b"preview")
    rows = [
        {"row_index": 0, "text": "\uadf8\ud638", "local_bbox": [0, 595, 93, 681]},
        {"row_index": 1, "text": "Passage starts here", "local_bbox": [87, 768, 1312, 834]},
        {"row_index": 2, "text": "Passage continues", "local_bbox": [48, 847, 1314, 906]},
    ]
    (run_dir / "page_001_right.paddleocr.json").write_text(
        json.dumps({"local_size": [1392, 4415], "rows": rows}),
        encoding="utf-8",
    )
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
                        "column": "right",
                        "block_id": "p001_right",
                        "included_row_ids": ["p001_right_r000", "p001_right_r001", "p001_right_r002"],
                    }
                ],
            }
        ],
    }
    suggestions_path = run_dir / "suggestions.json"
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")

    passage = state.candidates[0]
    assert "\uadf8\ud638" not in passage.raw_ocr_text
    assert passage.verified_text == "Passage starts here Passage continues"


def test_question_prefill_recovers_omitted_choice_marker_inside_crop_bbox(tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "question_crop_suggestions" / "run"
    (run_dir / "q02_candidate").mkdir(parents=True)
    (run_dir / "q02_candidate" / "q02_candidate_preview.png").write_bytes(b"preview")
    rows = [
        {"row_index": 0, "text": "2. Question stem?", "local_bbox": [100, 10, 900, 40]},
        {"row_index": 1, "text": "1 Choice one", "local_bbox": [100, 60, 900, 90]},
        {"row_index": 2, "text": "2", "local_bbox": [100, 110, 130, 140]},
        {"row_index": 3, "text": "Choice two", "local_bbox": [150, 110, 900, 140]},
        {"row_index": 4, "text": "3Choice three", "local_bbox": [100, 160, 900, 190]},
        {"row_index": 5, "text": "4Choice four", "local_bbox": [100, 210, 900, 240]},
        {"row_index": 6, "text": "5Choice five", "local_bbox": [100, 260, 900, 290]},
    ]
    (run_dir / "page_002_left.paddleocr.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    payload = {
        "artifact_type": "candidate_question_crop_suggestions",
        "suggestions": [
            {
                "suggestion_id": "q02",
                "kind": "candidate_question_crop_suggestion",
                "question_number": 2,
                "candidate_preview_path": "q02_candidate/q02_candidate_preview.png",
                "parts": [
                    {
                        "page": 2,
                        "column": "left",
                        "block_id": "p002_left",
                        "local_crop_bbox": [80, 0, 920, 300],
                        "included_row_ids": [
                            "p002_left_r000",
                            "p002_left_r001",
                            "p002_left_r003",
                            "p002_left_r004",
                            "p002_left_r005",
                            "p002_left_r006",
                        ],
                    }
                ],
            }
        ],
    }
    suggestions_path = run_dir / "suggestions.json"
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")

    question = state.candidates[0]
    assert question.raw_ocr_text == "2. Question stem?\n1 Choice one\n2\nChoice two\n3Choice three\n4Choice four\n5Choice five"
    assert question.choices == ["Choice one", "Choice two", "Choice three", "Choice four", "Choice five"]


def test_question_prefill_uses_bbox_when_included_rows_are_empty(tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "question_crop_suggestions" / "run"
    (run_dir / "q03_candidate").mkdir(parents=True)
    (run_dir / "q03_candidate" / "q03_candidate_preview.png").write_bytes(b"preview")
    rows = [
        {"row_index": 0, "text": "outside", "local_bbox": [100, 10, 900, 40]},
        {"row_index": 1, "text": "3. Bbox question?", "local_bbox": [100, 60, 900, 90]},
        {"row_index": 2, "text": "1) One", "local_bbox": [100, 110, 900, 140]},
        {"row_index": 3, "text": "2) Two", "local_bbox": [100, 160, 900, 190]},
        {"row_index": 4, "text": "3) Three", "local_bbox": [100, 210, 900, 240]},
        {"row_index": 5, "text": "4) Four", "local_bbox": [100, 260, 900, 290]},
        {"row_index": 6, "text": "5) Five", "local_bbox": [100, 310, 900, 340]},
    ]
    (run_dir / "page_003_left.paddleocr.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    payload = {
        "artifact_type": "candidate_question_crop_suggestions",
        "suggestions": [
            {
                "suggestion_id": "q03",
                "kind": "candidate_question_crop_suggestion",
                "question_number": 3,
                "candidate_preview_path": "q03_candidate/q03_candidate_preview.png",
                "parts": [
                    {
                        "page": 3,
                        "column": "left",
                        "block_id": "p003_left",
                        "local_crop_bbox": [80, 50, 920, 350],
                        "included_row_ids": [],
                    }
                ],
            }
        ],
    }
    suggestions_path = run_dir / "suggestions.json"
    suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

    state = initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=tmp_path / "data")

    question = state.candidates[0]
    assert question.raw_ocr_text == "3. Bbox question?\n1) One\n2) Two\n3) Three\n4) Four\n5) Five"
    assert question.stem == "Bbox question?"


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


def test_passage_prefill_preserves_blank_line_paragraph_breaks() -> None:
    raw = "Alpha line one\nAlpha line two\n\nBeta line one\nBeta line two"

    draft = generate_ocr_draft(CandidateType.PASSAGE, raw)

    assert draft.verified_text == "Alpha line one Alpha line two\n\nBeta line one Beta line two"
    assert "joined_forced_line_breaks" in draft.correction_steps


def test_passage_prefill_joins_prose_rows_within_paragraph() -> None:
    raw = (
        "제도의 선택에 대한 설명에는,합리적인 주체인 사회 구성원들\n"
        "이 사회 전체적으로 가장 이익이 되는 제도를 채택한다고 보는\n"
        "효율성 시각과 이데올로기·경로의존성·정치적 과정 등으로 인해\n"
        "효율적 제도의 선택이 일반적이지 않다고 보는 시각이 있다."
    )

    draft = generate_ocr_draft(CandidateType.PASSAGE, raw)

    assert draft.verified_text == (
        "제도의 선택에 대한 설명에는, 합리적인 주체인 사회 구성원들이 사회 전체적으로 가장 이익이 되는 제도를 "
        "채택한다고 보는 효율성 시각과 이데올로기·경로의존성·정치적 과정 등으로 인해 효율적 제도의 선택이 "
        "일반적이지 않다고 보는 시각이 있다."
    )


def test_passage_prefill_joins_korean_words_split_by_line_wraps() -> None:
    raw = (
        "진실을 다\n룰 능력\n존재\n한다는 주장\n그러\n나 전자는\n믿\n는 바\n법적\n으로 인정\n무효로\n할 근거\n"
        "보장하는\n해석론\n현대의\n민주국가"
    )

    draft = generate_ocr_draft(CandidateType.PASSAGE, raw)

    assert (
        draft.verified_text
        == "진실을 다룰 능력 존재한다는 주장 그러나 전자는 믿는 바 법적으로 인정 무효로 할 근거 보장하는 해석론 현대의 민주국가"
    )
    assert "joined_forced_line_breaks" in draft.correction_steps


def test_passage_prefill_preserves_script_rows() -> None:
    raw = (
        "(나)\n"
        "[부산에 도착한 첫날 밤 세 가족은 파티를 연다.]\n"
        "창수댁:(한쪽이 터진 트렁크를 들고)여보,이것 좀 보세요.뚜껑\n"
        "을 덮으니까 또 터지겠죠.(돌아보지 않는 창수를 보고)\n"
        "아니 여보,당신은 남의 것을 보듯 거들떠보지도 않는구려.\n"
        "(창수, 외면하고 서 있다.)\n"
        "창 수:인젠 제에발 그 구질구질한 짐짝을 끌구 다니지 말자구\n"
        "했잖소.[] 바다 깊이 때 묻은 과거를 수장해 버리란\n"
        "말요.새로운 옷을 입으려거든 낡은 것을 미련 없이 벗어\n"
        "버려야하는 거야.\n"
        "모 두:(술잔을 쳐들고) 브라보!\n"
        "-김자림,[이민선]-"
    )

    draft = generate_ocr_draft(CandidateType.PASSAGE, raw)

    assert draft.verified_text == (
        "(나)\n"
        "[부산에 도착한 첫날 밤 세 가족은 파티를 연다.]\n"
        "창수댁: (한쪽이 터진 트렁크를 들고)여보, 이것 좀 보세요. 뚜껑을 덮으니까 또 터지겠죠.(돌아보지 않는 창수를 보고) 아니 여보, 당신은 남의 것을 보듯 거들떠보지도 않는구려.\n"
        "(창수, 외면하고 서 있다.)\n"
        "창 수: 인젠 제에발 그 구질구질한 짐짝을 끌구 다니지 말자구 했잖소.[] 바다 깊이 때 묻은 과거를 수장해 버리란 말요. 새로운 옷을 입으려거든 낡은 것을 미련 없이 벗어 버려야하는 거야.\n"
        "모 두: (술잔을 쳐들고) 브라보!\n"
        "-김자림, [이민선]-"
    )


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


def test_question_prefill_preserves_view_heading_and_item_paragraphs() -> None:
    raw = (
        "14. \ubb38\uc81c \uc9c8\ubb38\n"
        "<\ubcf4\uae30>\uc5d0\uc11c\n"
        "\uc788\ub294 \ub300\ub85c \uace0\ub978 \uac83\uc740?\n"
        "<\ubcf4 \uae30>\n"
        "\u3131. \uccab \ubb38\uc7a5\n"
        "\uc774\uc5b4\uc9c4 \ubb38\uc7a5\n"
        "\u3134. \ub458\uc9f8 \ubb38\uc7a5\n"
        "\uc774\uc5b4\uc9d0\n"
        "\u3137. \uc14b\uc9f8 \ubb38\uc7a5\n"
        "1 \u3131\n"
        "2 \u3134\n"
        "3 \u3137\n"
        "4 \u3131, \u3134\n"
        "5 \u3131, \u3134, \u3137"
    )

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=14)

    assert draft.stem == (
        "\ubb38\uc81c \uc9c8\ubb38 <\ubcf4\uae30>\uc5d0\uc11c \uc788\ub294 \ub300\ub85c \uace0\ub978 \uac83\uc740?\n"
        "<\ubcf4 \uae30>\n"
        "\u3131. \uccab \ubb38\uc7a5 \uc774\uc5b4\uc9c4 \ubb38\uc7a5\n"
        "\u3134. \ub458\uc9f8 \ubb38\uc7a5 \uc774\uc5b4\uc9d0\n"
        "\u3137. \uc14b\uc9f8 \ubb38\uc7a5"
    )


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


def test_question_prefill_continues_after_missing_middle_choice_marker() -> None:
    raw = (
        "2. Question stem?\n"
        "1 Choice one\n"
        "Choice two text with missing marker\n"
        "3Choice three\n"
        "4Choice four\n"
        "5Choice five"
    )

    draft = generate_ocr_draft(CandidateType.QUESTION, raw, question_number=2)

    assert draft.choices[0] == "Choice one Choice two text with missing marker"
    assert draft.choices[1] == ""
    assert draft.choices[2] == "Choice three"
    assert draft.choices[3] == "Choice four"
    assert draft.choices[4] == "Choice five"
    assert "choices_detected_4" in draft.warnings
    assert "ignored_out_of_sequence_choice_markers:2" in draft.warnings


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


def test_kiwipiepy_spacing_backend_records_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeKiwi:
        def space(self, text: str) -> str:
            return text.replace("withoutspace", "without space")

    def fake_import(name: str):
        if name == "kiwipiepy":
            return SimpleNamespace(Kiwi=lambda: FakeKiwi())
        raise ImportError(name)

    monkeypatch.setattr(verification, "import_module", fake_import)

    draft = generate_ocr_draft(
        CandidateType.PASSAGE,
        "withoutspace",
        options=DraftOptions(enable_spacing_cleanup=True),
    )

    assert draft.verified_text == "without space"
    assert "spacing_cleanup:kiwipiepy" in draft.correction_steps
