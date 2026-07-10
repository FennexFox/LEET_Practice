from __future__ import annotations

import argparse
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import build_tagging_dashboard as dashboard


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LANGUAGE_SECTION = "\uc5b8\uc5b4\uc774\ud574"
REASONING_SECTION = "\ucd94\ub9ac\ub17c\uc99d"
SECTION_ALIASES = {
    LANGUAGE_SECTION: [LANGUAGE_SECTION, "\uc5b8\uc5b4"],
    REASONING_SECTION: [REASONING_SECTION, "\ucd94\ub9ac"],
}


class TaggingDashboardHandler(BaseHTTPRequestHandler):
    server_version = "LEETTaggingDashboard/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/tagging-dashboard", "/docs/tagging-dashboard.html"}:
            self._send_dashboard_html()
            return
        if path == "/review":
            self._send_review_html()
            return
        if path == "/api/dashboard":
            self._send_dashboard_json()
            return
        if path == "/healthz":
            self._send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send_dashboard_html(self) -> None:
        try:
            output = dashboard.build_current_dashboard_html()
            dashboard.validate_html(output)
        except Exception as exc:
            self._send_error(exc, wants_json=False)
            return
        self._send_bytes(output.encode("utf-8"), "text/html; charset=utf-8")

    def _send_review_html(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        review_file = (query.get("file") or [""])[0]
        try:
            output = build_review_page(review_file)
        except Exception as exc:
            self._send_error(exc, wants_json=False)
            return
        self._send_bytes(output.encode("utf-8"), "text/html; charset=utf-8")

    def _send_dashboard_json(self) -> None:
        try:
            payload = dashboard.build_dashboard_data()
        except Exception as exc:
            self._send_error(exc, wants_json=True)
            return
        self._send_json(payload)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status=status)

    def _send_error(self, exc: Exception, wants_json: bool) -> None:
        if wants_json:
            self._send_json(
                {"error": type(exc).__name__, "message": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        body = (
            "<!doctype html><meta charset=\"utf-8\">"
            "<title>Dashboard error</title>"
            "<h1>Dashboard error</h1>"
            f"<pre>{type(exc).__name__}: {dashboard.h(str(exc))}</pre>"
        ).encode("utf-8")
        self._send_bytes(body, "text/html; charset=utf-8", status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def resolve_review_path(review_file: str) -> Path:
    if not review_file:
        raise ValueError("Missing review file")
    root = dashboard.ROOT.resolve()
    review_root = (root / "data" / "reviews").resolve()
    path = (root / review_file).resolve()
    if not path.is_relative_to(review_root):
        raise ValueError("Review file must be under data/reviews")
    if not path.name.endswith(".review.json"):
        raise ValueError("Review file must end with .review.json")
    if not path.exists():
        raise FileNotFoundError(review_file)
    return path


def infer_year_section(review: dict[str, Any], review_path: Path) -> tuple[int | None, str | None]:
    text = " ".join(
        str(value)
        for value in [
            review.get("exam_id"),
            review.get("attempt_id"),
            review.get("question_id"),
            review_path.as_posix(),
        ]
        if value
    )
    year_match = re.search(r"\b(20\d{2})\b", text)
    section = None
    if LANGUAGE_SECTION in text:
        section = LANGUAGE_SECTION
    elif REASONING_SECTION in text:
        section = REASONING_SECTION
    return (int(year_match.group(1)) if year_match else None, section)


def load_jsonl_item(path: Path, key: str, value: Any) -> dict[str, Any] | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get(key) == value:
            return item
    return None


def load_canonical_question(review: dict[str, Any], review_path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    year, section = infer_year_section(review, review_path)
    question_no = review.get("question_no")
    if year is None or section is None or question_no is None:
        return None, None
    section_aliases = SECTION_ALIASES.get(section, [section])
    canonical_dir = next(
        (
            path
            for path in (dashboard.ROOT / "data" / "canonical").iterdir()
            if path.is_dir()
            and path.name.startswith(str(year))
            and any(alias in path.name for alias in section_aliases)
        ),
        None,
    )
    if canonical_dir is None:
        return None, None
    question = load_jsonl_item(canonical_dir / "questions.jsonl", "question_no", question_no)
    passage = None
    if question and question.get("passage_id"):
        passage = load_jsonl_item(canonical_dir / "passages.jsonl", "id", question["passage_id"])
    return question, passage


def find_tagging_record(review_file: str) -> dict[str, Any] | None:
    normalized = review_file.replace("\\", "/")
    for record in dashboard.load_records():
        if record.get("review_file") == normalized:
            return record
    return None


def build_review_page(review_file: str) -> str:
    review_path = resolve_review_path(review_file)
    relative_review_file = review_path.relative_to(dashboard.ROOT).as_posix()
    review = json.loads(review_path.read_text(encoding="utf-8"))
    question, passage = load_canonical_question(review, review_path)
    tagging_record = find_tagging_record(relative_review_file)
    grading = review.get("grading") or {}
    correct_choice = grading.get("correct_choice") or (question or {}).get("correct_answer")
    selected_choice = grading.get("selected_choice")
    title = f"{review.get('exam_id') or review.get('attempt_id') or 'Review'} Q{int(review.get('question_no') or 0):02d}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{dashboard.h(title)} - Review</title>
  <style>{dashboard.CSS}{REVIEW_CSS}</style>
</head>
<body>
  <header class="app-header">
    <h1>{dashboard.h(title)}</h1>
    <nav><a href="/">Dashboard</a><a href="/api/dashboard">API</a></nav>
  </header>
  <main class="review-main">
    <section>
      <h2>Review File</h2>
      <p><code>{dashboard.h(relative_review_file)}</code></p>
      {render_tagging_summary(tagging_record)}
    </section>
    {render_question_block(question, passage)}
    {render_retry_block(question, correct_choice)}
    {render_review_block(review, selected_choice, correct_choice)}
  </main>
  <script>{REVIEW_JS}</script>
</body>
</html>
"""


def render_tagging_summary(record: dict[str, Any] | None) -> str:
    if not record:
        return '<p class="note">No provisional tagging record is linked to this review file.</p>'
    tags = record.get("provisional_tags") or {}
    secondary = ", ".join(tags.get("secondary") or []) or "none"
    return f"""
    <dl class="review-summary">
      <div><dt>Primary tag</dt><dd><code>{dashboard.h(tags.get("primary"))}</code></dd></div>
      <div><dt>Secondary tags</dt><dd><code>{dashboard.h(secondary)}</code></dd></div>
      <div><dt>Confidence</dt><dd>{dashboard.h(tags.get("confidence"))}</dd></div>
    </dl>
    <p>{dashboard.h(record.get("tag_rationale"))}</p>
    """


def render_retry_block(question: dict[str, Any] | None, correct_choice: Any) -> str:
    if not question or not question.get("choices"):
        return """
        <section>
          <h2>Retry</h2>
          <p class="note">Canonical choices were not found, so this review cannot be retried here.</p>
        </section>
        """
    choices = "\n".join(
        f"""
        <label class="choice-option">
          <input type="radio" name="retry-choice" value="{dashboard.h(choice.get('choice_no'))}">
          <span>{dashboard.h(choice.get('choice_no'))}. {dashboard.h(choice.get('text'))}</span>
        </label>
        """
        for choice in question["choices"]
    )
    return f"""
    <section class="retry-panel" data-correct="{dashboard.h(correct_choice)}">
      <h2>Retry</h2>
      <p>Choose an answer, then check it locally. This does not modify the review file.</p>
      <fieldset>{choices}</fieldset>
      <button id="checkAnswer" type="button">Check Answer</button>
      <strong id="retryResult" aria-live="polite"></strong>
    </section>
    """


def render_question_block(question: dict[str, Any] | None, passage: dict[str, Any] | None) -> str:
    if not question:
        return """
        <section>
          <h2>Canonical Question</h2>
          <p class="note">Canonical question data was not found for this review.</p>
        </section>
        """
    passage_html = ""
    if passage:
        passage_html = f"""
        <details>
          <summary>Passage {dashboard.h(passage.get("id"))}</summary>
          <pre class="question-text">{dashboard.h(passage.get("body_text"))}</pre>
        </details>
        """
    return f"""
    <section>
      <h2>Canonical Question</h2>
      {passage_html}
      <pre class="question-text">{dashboard.h(question.get("stem"))}</pre>
    </section>
    """


def render_review_block(review: dict[str, Any], selected_choice: Any, correct_choice: Any) -> str:
    user_review = review.get("user_self_review") or {}
    feedback = review.get("assistant_feedback") or {}
    evidence = feedback.get("evidence") or []
    evidence_html = "".join(f"<li>{dashboard.h(item)}</li>" for item in evidence)
    return f"""
    <section>
      <h2>Original Review</h2>
      <dl class="review-summary">
        <div><dt>Selected</dt><dd>{dashboard.h(selected_choice)}</dd></div>
        <div><dt>Correct</dt><dd>{dashboard.h(correct_choice)}</dd></div>
        <div><dt>Status</dt><dd>{dashboard.h(review.get("status"))}</dd></div>
      </dl>
      <details>
        <summary>User self-review</summary>
        <p>{dashboard.h(user_review.get("reasoning_text"))}</p>
        <p>{dashboard.h(user_review.get("current_reflection"))}</p>
      </details>
      <details>
        <summary>Assistant feedback</summary>
        <p>{dashboard.h(feedback.get("diagnosis_text"))}</p>
        <ul>{evidence_html}</ul>
        <p><strong>Correction rule:</strong> {dashboard.h(feedback.get("correction_rule"))}</p>
      </details>
    </section>
    """


REVIEW_CSS = """
.review-main { max-width: 1100px; }
.review-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }
.review-summary div { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.review-summary dt { color: var(--muted); font-size: 12px; }
.review-summary dd { margin: 4px 0 0; font-weight: 700; }
.retry-panel fieldset { border: 0; padding: 0; margin: 0 0 12px; display: grid; gap: 8px; }
.choice-option { display: flex; gap: 8px; align-items: flex-start; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.choice-option input { margin-top: 3px; }
button { border: 1px solid var(--accent); background: var(--accent); color: white; border-radius: 6px; padding: 8px 12px; font-weight: 700; cursor: pointer; }
#retryResult { margin-left: 10px; }
.question-text { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; font-family: inherit; line-height: 1.55; }
"""


REVIEW_JS = """
const checkButton = document.getElementById('checkAnswer');
if (checkButton) {
  checkButton.addEventListener('click', () => {
    const panel = document.querySelector('.retry-panel');
    const selected = document.querySelector('input[name="retry-choice"]:checked');
    const result = document.getElementById('retryResult');
    if (!selected) {
      result.textContent = 'Choose an answer first.';
      result.style.color = 'var(--warn)';
      return;
    }
    const correct = panel.dataset.correct;
    const isCorrect = selected.value === correct;
    result.textContent = isCorrect ? 'Correct.' : `Incorrect. Correct answer: ${correct}`;
    result.style.color = isCorrect ? 'var(--accent)' : 'var(--danger)';
  });
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the LEET tagging dashboard from live repo data.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), TaggingDashboardHandler)
    url = f"http://{args.host}:{server.server_port}/"
    print(f"Serving live tagging dashboard at {url}")
    print("API endpoint: /api/dashboard")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
