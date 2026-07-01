from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from pathlib import Path

from leet_practice.verification import create_review_server, initialize_review_state, review_state_path


def test_workbench_serves_state_preview_and_updates(tmp_path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)
    server = create_review_server("leet-2026-verbal-even", data_root=data_root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        root = urllib.request.urlopen(f"{base_url}/", timeout=5).read().decode("utf-8")
        assert "LEET Verification Workbench" in root
        assert 'id="passageFields"' in root
        assert 'id="questionFields"' in root
        assert 'id="question_number"' in root
        assert 'scheduleAutosave' in root
        assert 'id="copyRaw"' in root

        state = json.loads(urllib.request.urlopen(f"{base_url}/api/state", timeout=5).read().decode("utf-8"))
        assert len(state["candidates"]) == 2

        preview = urllib.request.urlopen(f"{base_url}/preview/q01", timeout=5).read()
        assert preview == b"preview"

        request = urllib.request.Request(
            f"{base_url}/api/candidates/q01",
            method="POST",
            data=json.dumps({"status": "needs_fix", "notes": "crop too narrow"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        updated = json.loads(urllib.request.urlopen(request, timeout=5).read().decode("utf-8"))
        assert updated["status"] == "needs_fix"
        assert updated["notes"] == "crop too narrow"

        bad_request = urllib.request.Request(
            f"{base_url}/api/candidates/q01",
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


def test_workbench_rejects_preview_paths_outside_suggestions_dir(tmp_path, suggestion_run: Path) -> None:
    suggestions_path = suggestion_run
    data_root = tmp_path / "data"
    initialize_review_state("leet-2026-verbal-even", suggestions_path, data_root=data_root)
    outside_file = tmp_path / "outside.png"
    outside_file.write_bytes(b"secret")
    state_path = review_state_path("leet-2026-verbal-even", data_root=data_root)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["candidates"][1]["preview_path"] = str(outside_file)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    server = create_review_server("leet-2026-verbal-even", data_root=data_root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        try:
            urllib.request.urlopen(f"{base_url}/preview/q01", timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("preview paths outside suggestions dir should fail with HTTP 404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
