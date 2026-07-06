from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from leet_practice.attempt_review import create_attempt_record, create_review_server, initialize_attempt_reviews


def _write_canonical(data_root: Path, exam_id: str) -> None:
    canonical_dir = data_root / "canonical" / exam_id
    canonical_dir.mkdir(parents=True)
    (canonical_dir / "answer_key.json").write_text(json.dumps({"answers": {"1": 3}}), encoding="utf-8")
    row = {
        "id": f"{exam_id}-q001",
        "exam_id": exam_id,
        "question_no": 1,
        "passage_id": f"{exam_id}-passage-001",
        "stem": "Which choice follows?\n\nRead the passage carefully.",
        "choices": [
            {"choice_no": index, "text": f"Choice {index}\nsecond line"}
            for index in range(1, 6)
        ],
        "correct_answer": 3,
    }
    (canonical_dir / "questions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    passage = {
        "id": f"{exam_id}-passage-001",
        "exam_id": exam_id,
        "passage_no": 1,
        "question_range": [1, 1],
        "body_text": "Passage paragraph one.\n\nPassage paragraph two.",
    }
    (canonical_dir / "passages.jsonl").write_text(json.dumps(passage) + "\n", encoding="utf-8")


def test_attempt_review_workbench_serves_state_and_updates_review(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exam_id = "leet-2026-reasoning-even"
    _write_canonical(data_root, exam_id)
    create_attempt_record("attempt-001", exam_id, "1", data_root=data_root)
    initialize_attempt_reviews("attempt-001", data_root=data_root)
    server = create_review_server("attempt-001", data_root=data_root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        root = urllib.request.urlopen(f"{base_url}/", timeout=5).read().decode("utf-8")
        assert "LEET Attempt Review" in root
        assert "reasoning_text" in root
        assert "memory_confidence" in root
        assert "choiceNumber" in root
        assert 'padStart(2, "0")' in root
        assert "white-space: pre-wrap" in root
        assert "choice-text" in root
        assert "passageBox" in root
        assert "passage-text" in root
        assert "Free-form reconstruction" in root
        assert "Your current post-hoc understanding" in root
        assert "diagnosis.textContent" in root
        assert "createTextNode(feedback.correction_rule" in root

        state = json.loads(urllib.request.urlopen(f"{base_url}/api/state", timeout=5).read().decode("utf-8"))
        assert state["score"] == 0
        assert state["wrong_question_numbers"] == [1]
        assert state["reviews"][0]["grading"]["correct_choice"] == 3
        assert state["questions"]["1"]["stem"] == "Which choice follows?\n\nRead the passage carefully."
        assert state["questions"]["1"]["passage_text"] == "Passage paragraph one.\n\nPassage paragraph two."
        assert state["questions"]["1"]["choices"][0]["text"] == "Choice 1\nsecond line"

        request = urllib.request.Request(
            f"{base_url}/api/reviews/1/self-review",
            method="POST",
            data=json.dumps(
                {
                    "reasoning_text": "Surface match.",
                    "current_reflection": "Need to compare the condition.",
                    "memory_confidence": "clear",
                    "status": "ready_for_feedback",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        updated = json.loads(urllib.request.urlopen(request, timeout=5).read().decode("utf-8"))
        assert updated["status"] == "ready_for_feedback"
        assert updated["user_self_review"]["reasoning_text"] == "Surface match."
        assert updated["user_self_review"]["current_reflection"] == "Need to compare the condition."
        assert updated["user_self_review"]["memory_confidence"] == "clear"

        invalid_status_request = urllib.request.Request(
            f"{base_url}/api/reviews/1/self-review",
            method="POST",
            data=json.dumps({"status": "feedback_added"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(invalid_status_request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("self-review should reject non-user-entry statuses")

        resolution_request = urllib.request.Request(
            f"{base_url}/api/reviews/1/resolution",
            method="POST",
            data=json.dumps({"status": "rejected", "note": "Not quite right"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        resolved = json.loads(urllib.request.urlopen(resolution_request, timeout=5).read().decode("utf-8"))
        assert resolved["status"] == "resolved"
        assert resolved["user_resolution"]["status"] == "rejected"

        bad_request = urllib.request.Request(
            f"{base_url}/api/reviews/1/self-review",
            method="POST",
            data=b"{",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(bad_request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("malformed JSON should fail with HTTP 400")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
