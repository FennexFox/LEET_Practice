from __future__ import annotations

import json
import threading
import urllib.request

from leet_practice.verification import create_review_server, initialize_review_state
from tests.test_verification_storage import make_suggestion_run


def test_workbench_serves_state_preview_and_updates(tmp_path) -> None:
    suggestions_path = make_suggestion_run(tmp_path)
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
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
