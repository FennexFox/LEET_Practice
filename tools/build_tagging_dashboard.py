from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TAGGING_DIR = ROOT / "data" / "tagging"
RECORDS_PATH = TAGGING_DIR / "provisional_tags.jsonl"
FINAL_TAG_DOC = TAGGING_DIR / "final_tag_dictionary.v1.md"
SUPPORTING_TAG_DOC = TAGGING_DIR / "supporting_status_tags.v1.md"
PROVISIONAL_TAG_DOC = TAGGING_DIR / "tag_dictionary.provisional.md"
OUTPUT_PATH = ROOT / "docs" / "tagging-dashboard.html"

FINAL_V1_TAGS = [
    "SCOPE_CONDITION_MISAPPLICATION",
    "CONCEPT_LAYER_CONFUSION",
    "ARGUMENT_STRUCTURE_INCOMPLETE",
    "FORMAL_CONDITION_ERROR",
    "GLOBAL_CONSTRAINT_DROPPED",
    "TABLE_DIAGRAM_ENCODING_ERROR",
    "RELATION_DIRECTION_REVERSAL",
    "TEXTUAL_REDEFINITION_MISSED",
    "UNWARRANTED_ASSUMPTION_ADDED",
]
SUPPORTING_STATUS_TAGS = {
    "CHOICE_VERIFICATION_FAILURE": "supporting tag",
    "TIME_PRESSURE_OR_ATTENTION_LAPSE": "operational modifier",
    "INSUFFICIENT_REVIEW_BASIS": "data-quality/status tag",
}
SECTION_IDS = [
    "overview",
    "tag-frequency",
    "final-tags",
    "supporting-status-tags",
    "year-section-breakdown",
    "records-table",
    "review-queue",
    "representative-cases",
    "audit",
]


def load_records(path: Path = RECORDS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing tagging JSONL: {path}")
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on {path}:{line_no}: {exc}") from exc
    if not records:
        raise ValueError(f"No tagging records found in {path}")
    return records


def _parse_bullets(section: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in section.splitlines():
        match = re.match(r"- ([^:]+):\s*(.*)", line.strip())
        if match:
            values[match.group(1).strip().lower()] = match.group(2).strip()
    return values


def parse_provisional_doc(path: Path = PROVISIONAL_TAG_DOC) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    tags: dict[str, dict[str, str]] = {}
    for match in re.finditer(r"^## `([^`]+)`\s*$", text, re.MULTILINE):
        tag_id = match.group(1)
        start = match.end()
        next_match = re.search(r"^## `", text[start:], re.MULTILINE)
        end = start + next_match.start() if next_match else len(text)
        bullets = _parse_bullets(text[start:end])
        tags[tag_id] = {
            "tag_id": tag_id,
            "korean": bullets.get("korean display name", ""),
            "definition": bullets.get("definition", ""),
            "correction_rule": bullets.get("suggested correction rule", ""),
        }
    return tags


def parse_final_doc(path: Path = FINAL_TAG_DOC) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    tags: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "| `" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        tag_match = re.search(r"`([^`]+)`", cells[0])
        if not tag_match:
            continue
        tag_id = tag_match.group(1)
        tags[tag_id] = {
            "tag_id": tag_id,
            "korean": cells[1],
            "definition": cells[2],
        }
    return tags


def parse_supporting_doc(path: Path = SUPPORTING_TAG_DOC) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    tags: dict[str, dict[str, str]] = {}
    for match in re.finditer(r"^### `([^`]+)`\s*$", text, re.MULTILINE):
        tag_id = match.group(1)
        start = match.end()
        next_match = re.search(r"^### `", text[start:], re.MULTILINE)
        end = start + next_match.start() if next_match else len(text)
        bullets = _parse_bullets(text[start:end])
        tags[tag_id] = {
            "tag_id": tag_id,
            "korean": bullets.get("korean display name", ""),
            "role": bullets.get("role", SUPPORTING_STATUS_TAGS.get(tag_id, "")),
            "definition": bullets.get("meaning", ""),
            "correction_rule": bullets.get("correction rule", ""),
        }
    return tags


def classify_tags() -> dict[str, dict[str, str]]:
    provisional = parse_provisional_doc()
    final_doc = parse_final_doc()
    supporting_doc = parse_supporting_doc()
    metadata: dict[str, dict[str, str]] = {}

    for tag_id in FINAL_V1_TAGS:
        doc = final_doc.get(tag_id, {})
        fallback = provisional.get(tag_id, {})
        metadata[tag_id] = {
            "tag_id": tag_id,
            "class": "final",
            "role": "final v1 mechanism tag",
            "korean": doc.get("korean") or fallback.get("korean", ""),
            "definition": doc.get("definition") or fallback.get("definition", ""),
            "correction_rule": fallback.get("correction_rule", "Confirm against representative cases before promotion."),
        }

    for tag_id, default_role in SUPPORTING_STATUS_TAGS.items():
        doc = supporting_doc.get(tag_id, {})
        fallback = provisional.get(tag_id, {})
        tag_class = "status" if "status" in default_role or "quality" in default_role else "supporting"
        metadata[tag_id] = {
            "tag_id": tag_id,
            "class": tag_class,
            "role": doc.get("role") or default_role,
            "korean": doc.get("korean") or fallback.get("korean", ""),
            "definition": doc.get("definition") or fallback.get("definition", ""),
            "correction_rule": doc.get("correction_rule") or fallback.get("correction_rule", ""),
        }

    for tag_id, fallback in provisional.items():
        metadata.setdefault(
            tag_id,
            {
                "tag_id": tag_id,
                "class": "provisional",
                "role": "provisional-only tag",
                "korean": fallback.get("korean", ""),
                "definition": fallback.get("definition", ""),
                "correction_rule": fallback.get("correction_rule", ""),
            },
        )

    missing = [tag_id for tag_id in FINAL_V1_TAGS if not metadata.get(tag_id, {}).get("definition")]
    if missing:
        raise ValueError(f"Final v1 tag metadata could not be constructed: {missing}")
    missing_supporting = [tag_id for tag_id in SUPPORTING_STATUS_TAGS if tag_id not in metadata]
    if missing_supporting:
        raise ValueError(f"Supporting/status tag metadata could not be constructed: {missing_supporting}")
    return metadata


def compute_counts(records: list[dict[str, Any]], metadata: dict[str, dict[str, str]]) -> dict[str, Any]:
    active = [record for record in records if record.get("use_for_tag_frequency") is True]
    holdouts = [record for record in records if record.get("holdout") is True]
    return {
        "total_records": len(records),
        "active_records": len(active),
        "holdout_records": len(holdouts),
        "needs_review_records": sum(1 for record in records if record.get("needs_review") is True),
        "needs_review_non_holdout": sum(
            1
            for record in records
            if record.get("needs_review") is True and record.get("holdout") is not True
        ),
        "final_tag_count": sum(1 for tag in metadata.values() if tag["class"] == "final"),
        "supporting_status_tag_count": len(SUPPORTING_STATUS_TAGS),
    }


def compute_tag_frequency(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [record for record in records if record.get("use_for_tag_frequency") is True]
    primary_counts = Counter(record["provisional_tags"]["primary"] for record in active)
    all_counts: Counter[str] = Counter()
    for record in active:
        all_counts[record["provisional_tags"]["primary"]] += 1
        all_counts.update(record["provisional_tags"].get("secondary") or [])
    return [
        {
            "tag_id": tag_id,
            "primary_count": count,
            "all_count": all_counts[tag_id],
            "primary_percent": round((count / len(active)) * 100, 1) if active else 0,
        }
        for tag_id, count in primary_counts.most_common()
    ]


def select_representative_cases(
    records: list[dict[str, Any]], tag_id: str, limit: int = 4
) -> list[dict[str, Any]]:
    active = [
        record
        for record in records
        if record.get("use_for_tag_frequency") is True
        and (
            record["provisional_tags"]["primary"] == tag_id
            or tag_id in (record["provisional_tags"].get("secondary") or [])
        )
    ]
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    active.sort(
        key=lambda record: (
            0 if record["provisional_tags"]["primary"] == tag_id else 1,
            confidence_rank.get(record["provisional_tags"].get("confidence"), 9),
            record.get("year") or 9999,
            record.get("section") or "",
            record.get("question_no") or 999,
        )
    )
    return active[:limit]


def compute_year_section_breakdown(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("use_for_tag_frequency") is True:
            groups[(record.get("year"), record.get("section") or "")].append(record)
    rows: list[dict[str, Any]] = []
    for (year, section), group in sorted(groups.items()):
        counts = Counter(record["provisional_tags"]["primary"] for record in group)
        rows.append(
            {
                "year": year,
                "section": section,
                "active_records": len(group),
                "top_tags": ", ".join(f"{tag} ({count})" for tag, count in counts.most_common(3)),
            }
        )
    return rows


def compute_review_queue(records: list[dict[str, Any]], metadata: dict[str, dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    active = [record for record in records if record.get("use_for_tag_frequency") is True]
    return {
        "holdouts": [record for record in records if record.get("holdout") is True],
        "needs_review_non_holdout": [
            record
            for record in records
            if record.get("needs_review") is True and record.get("holdout") is not True
        ],
        "low_confidence_active": [
            record for record in active if record["provisional_tags"].get("confidence") == "low"
        ],
        "supporting_or_status_primary": [
            record
            for record in active
            if metadata.get(record["provisional_tags"]["primary"], {}).get("class")
            in {"supporting", "status"}
        ],
    }


def validate_records(records: list[dict[str, Any]], metadata: dict[str, dict[str, str]]) -> dict[str, Any]:
    missing_review_file = [idx for idx, record in enumerate(records, 1) if not record.get("review_file")]
    missing_primary = [
        idx
        for idx, record in enumerate(records, 1)
        if not (record.get("provisional_tags") or {}).get("primary")
    ]
    holdout_frequency = [
        record["review_file"]
        for record in records
        if record.get("holdout") is True and record.get("use_for_tag_frequency") is True
    ]
    holdout_promotion = [
        record["review_file"]
        for record in records
        if record.get("holdout") is True and record.get("use_for_final_tag_promotion") is True
    ]
    final_missing = [tag_id for tag_id in FINAL_V1_TAGS if tag_id not in metadata]
    errors = []
    if missing_review_file:
        errors.append(f"records missing review_file: {missing_review_file}")
    if missing_primary:
        errors.append(f"records missing provisional_tags.primary: {missing_primary}")
    if holdout_frequency:
        errors.append(f"holdouts contributing to tag frequency: {holdout_frequency}")
    if holdout_promotion:
        errors.append(f"holdouts contributing to final promotion: {holdout_promotion}")
    if final_missing:
        errors.append(f"final v1 tags missing from metadata: {final_missing}")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "jsonl_records_parsed": len(records),
        "records_missing_review_file": len(missing_review_file),
        "records_missing_primary": len(missing_primary),
        "holdout_contributes_to_frequency": bool(holdout_frequency),
        "holdout_contributes_to_final_promotion": bool(holdout_promotion),
        "final_v1_tags_all_present": not final_missing,
    }


def h(text: Any) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def render_card(label: str, value: Any) -> str:
    return f'<div class="metric"><span>{h(label)}</span><strong>{h(value)}</strong></div>'


def render_tag_badge(tag_id: str, metadata: dict[str, dict[str, str]]) -> str:
    tag_class = metadata.get(tag_id, {}).get("class", "provisional")
    return f'<span class="tag-badge {h(tag_class)}">{h(tag_id)}</span>'


def render_record_link(record: dict[str, Any]) -> str:
    return f"{h(record.get('year'))} {h(record.get('section'))} q{int(record.get('question_no') or 0):02d}"


def build_dashboard_html(
    records: list[dict[str, Any]],
    stats: dict[str, Any],
    metadata: dict[str, dict[str, str]],
    tag_frequency: list[dict[str, Any]],
    audit: dict[str, Any],
) -> str:
    year_breakdown = compute_year_section_breakdown(records)
    review_queue = compute_review_queue(records, metadata)
    final_reps = {
        tag_id: select_representative_cases(records, tag_id, limit=4) for tag_id in FINAL_V1_TAGS
    }
    years = sorted({record.get("year") for record in records if record.get("year") is not None})
    sections = sorted({record.get("section") for record in records if record.get("section")})
    confidences = sorted({record["provisional_tags"].get("confidence") for record in records})
    all_tags = sorted(
        {
            tag
            for record in records
            for tag in [record["provisional_tags"]["primary"]]
            + list(record["provisional_tags"].get("secondary") or [])
        }
    )
    dashboard_data = {
        "records": records,
        "metadata": metadata,
        "stats": stats,
        "tagFrequency": tag_frequency,
        "audit": audit,
    }

    frequency_rows = "\n".join(
        "<tr>"
        f"<td>{render_tag_badge(row['tag_id'], metadata)}</td>"
        f"<td>{h(metadata.get(row['tag_id'], {}).get('role', 'provisional-only tag'))}</td>"
        f"<td>{row['primary_count']}</td>"
        f"<td>{row['all_count']}</td>"
        f"<td>{row['primary_percent']}%</td>"
        "</tr>"
        for row in tag_frequency
    )

    final_cards = "\n".join(
        f"""
        <article class="tag-card">
          <header>{render_tag_badge(tag_id, metadata)}<span>{h(metadata[tag_id].get('korean'))}</span></header>
          <p>{h(metadata[tag_id].get('definition'))}</p>
          <dl>
            <div><dt>Primary</dt><dd>{next((row['primary_count'] for row in tag_frequency if row['tag_id'] == tag_id), 0)}</dd></div>
            <div><dt>Primary + secondary</dt><dd>{next((row['all_count'] for row in tag_frequency if row['tag_id'] == tag_id), 0)}</dd></div>
          </dl>
          <p class="rule">{h(metadata[tag_id].get('correction_rule'))}</p>
          <ul>{''.join(f'<li>{h(case["review_file"])}</li>' for case in final_reps[tag_id][:3])}</ul>
        </article>
        """
        for tag_id in FINAL_V1_TAGS
    )

    support_cards = "\n".join(
        f"""
        <article class="tag-card supporting-card">
          <header>{render_tag_badge(tag_id, metadata)}<span>{h(metadata[tag_id].get('role'))}</span></header>
          <p>{h(metadata[tag_id].get('definition'))}</p>
          <p class="rule">{h(metadata[tag_id].get('correction_rule'))}</p>
          <p class="note">Not normally promoted as a primary final error mechanism.</p>
        </article>
        """
        for tag_id in SUPPORTING_STATUS_TAGS
    )

    breakdown_rows = "\n".join(
        f"<tr><td>{h(row['year'])}</td><td>{h(row['section'])}</td><td>{row['active_records']}</td><td>{h(row['top_tags'])}</td></tr>"
        for row in year_breakdown
    )

    queue_blocks = "\n".join(
        f"""
        <article class="queue-block">
          <h3>{h(title)} <span>{len(items)}</span></h3>
          <ul>{''.join(f'<li><strong>{render_record_link(record)}</strong> {h(record["review_file"])} <em>{h(record["provisional_tags"]["primary"])}</em></li>' for record in items)}</ul>
        </article>
        """
        for title, items in [
            ("Holdout records", review_queue["holdouts"]),
            ("Needs review excluding holdouts", review_queue["needs_review_non_holdout"]),
            ("Low-confidence active records", review_queue["low_confidence_active"]),
            ("Supporting/status primary records", review_queue["supporting_or_status_primary"]),
        ]
    )

    representative_blocks = "\n".join(
        f"""
        <section class="rep-group">
          <h3>{render_tag_badge(tag_id, metadata)}</h3>
          {''.join(render_case_details(case) for case in final_reps[tag_id])}
        </section>
        """
        for tag_id in FINAL_V1_TAGS
    )

    audit_rows = "\n".join(
        f"<tr><td>{h(key.replace('_', ' '))}</td><td>{h(value)}</td></tr>"
        for key, value in audit.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LEET Tagging Dashboard</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="app-header">
    <h1>LEET Tagging Dashboard</h1>
    <nav>{''.join(f'<a href="#{section_id}">{section_id.replace("-", " ").title()}</a>' for section_id in SECTION_IDS)}</nav>
  </header>
  <main>
    <section id="overview">
      <h2>Overview</h2>
      <div class="metrics">
        {render_card("Total wrong-answer records", stats["total_records"])}
        {render_card("Active records used for tag analysis", stats["active_records"])}
        {render_card("Holdout records", stats["holdout_records"])}
        {render_card("Needs-review records", stats["needs_review_records"])}
        {render_card("Needs-review excluding holdouts", stats["needs_review_non_holdout"])}
        {render_card("Final v1 mechanism tags", stats["final_tag_count"])}
        {render_card("Supporting/status tags", stats["supporting_status_tag_count"])}
      </div>
    </section>

    <section id="tag-frequency">
      <h2>Active Tag Frequency</h2>
      <p>Computed only from records where <code>use_for_tag_frequency</code> is true.</p>
      <table><thead><tr><th>Tag</th><th>Role</th><th>Primary</th><th>Primary + secondary</th><th>% active primary</th></tr></thead><tbody>{frequency_rows}</tbody></table>
    </section>

    <section id="final-tags">
      <h2>Final v1 Tags</h2>
      <div class="tag-grid">{final_cards}</div>
    </section>

    <section id="supporting-status-tags">
      <h2>Supporting and Status Tags</h2>
      <div class="tag-grid">{support_cards}</div>
    </section>

    <section id="year-section-breakdown">
      <h2>Year × Section Breakdown</h2>
      <table><thead><tr><th>Year</th><th>Section</th><th>Active records</th><th>Most frequent primary tags</th></tr></thead><tbody>{breakdown_rows}</tbody></table>
    </section>

    <section id="records-table">
      <h2>Records Table</h2>
      <div class="filters">
        <input id="searchInput" type="search" placeholder="Search records">
        <select id="tagFilter"><option value="">All tags</option>{''.join(f'<option>{h(tag)}</option>' for tag in all_tags)}</select>
        <select id="yearFilter"><option value="">All years</option>{''.join(f'<option>{h(year)}</option>' for year in years)}</select>
        <select id="sectionFilter"><option value="">All sections</option>{''.join(f'<option>{h(section)}</option>' for section in sections)}</select>
        <select id="confidenceFilter"><option value="">All confidence</option>{''.join(f'<option>{h(conf)}</option>' for conf in confidences)}</select>
        <label><input id="hideHoldouts" type="checkbox"> Hide holdouts</label>
        <label><input id="needsOnly" type="checkbox"> Needs-review only</label>
      </div>
      <div class="table-note"><span id="recordCount"></span></div>
      <table id="recordsTable">
        <thead><tr><th>Year</th><th>Section</th><th>Q</th><th>Review file</th><th>Selected</th><th>Correct</th><th>Primary tag</th><th>Secondary</th><th>Confidence</th><th>Needs review</th><th>Holdout</th><th>Use frequency</th><th>Use promotion</th><th>Rationale</th></tr></thead>
        <tbody></tbody>
      </table>
    </section>

    <section id="review-queue">
      <h2>Review Queue</h2>
      <div class="queue-grid">{queue_blocks}</div>
    </section>

    <section id="representative-cases">
      <h2>Representative Cases</h2>
      {representative_blocks}
    </section>

    <section id="audit">
      <h2>Data Integrity / Audit</h2>
      <table><tbody>{audit_rows}</tbody></table>
    </section>
  </main>
  <script id="dashboard-data" type="application/json">{html.escape(json.dumps(dashboard_data, ensure_ascii=False), quote=False)}</script>
  <script>{JS}</script>
</body>
</html>
"""


def render_case_details(record: dict[str, Any]) -> str:
    tags = record["provisional_tags"]
    canonical = record.get("canonical_basis") or {}
    review = record.get("review_basis") or {}
    summary = (
        f"{record.get('year')} {record.get('section')} q{int(record.get('question_no') or 0):02d} "
        f"selected {record.get('selected_choice')} / correct {record.get('correct_choice')} "
        f"({tags.get('confidence')})"
    )
    return f"""
    <details>
      <summary>{h(summary)} - {h(record.get('review_file'))}</summary>
      <p><strong>Rationale:</strong> {h(record.get('tag_rationale'))}</p>
      <p><strong>User self-diagnosis:</strong> {h(review.get('user_self_diagnosis_summary'))}</p>
      <p><strong>Assistant feedback:</strong> {h(review.get('assistant_feedback_summary'))}</p>
      <p><strong>Canonical basis:</strong> {h(canonical.get('question_summary'))} {h(canonical.get('key_evidence_pointer'))}</p>
    </details>
    """


CSS = """
:root {
  --bg: #f7f7f5;
  --panel: #ffffff;
  --text: #242424;
  --muted: #666;
  --line: #d9d9d4;
  --accent: #0f766e;
  --accent-2: #7c3aed;
  --warn: #b45309;
  --danger: #b91c1c;
  --mono: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); }
.app-header { position: sticky; top: 0; z-index: 2; background: #ffffffee; border-bottom: 1px solid var(--line); padding: 14px 24px; backdrop-filter: blur(8px); }
.app-header h1 { margin: 0 0 10px; font-size: 24px; letter-spacing: 0; }
nav { display: flex; flex-wrap: wrap; gap: 8px; }
nav a { color: var(--accent); text-decoration: none; font-size: 13px; border: 1px solid var(--line); padding: 5px 8px; border-radius: 6px; background: #fff; }
main { max-width: 1500px; margin: 0 auto; padding: 20px 24px 48px; }
section { margin: 0 0 26px; }
h2 { font-size: 20px; margin: 0 0 12px; }
h3 { font-size: 15px; margin: 0 0 10px; }
p { line-height: 1.45; }
code { font-family: var(--mono); background: #efefeb; padding: 1px 4px; border-radius: 4px; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }
.metric, .tag-card, .queue-block { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
.metric span { display: block; color: var(--muted); font-size: 12px; }
.metric strong { display: block; font-size: 28px; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); }
th, td { border-bottom: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; font-size: 13px; }
th { background: #efefeb; position: sticky; top: 84px; z-index: 1; }
.tag-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
.tag-card header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.tag-card p { margin: 8px 0; }
.tag-card dl { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0; }
.tag-card dl div { background: #f4f4f1; border-radius: 6px; padding: 8px; }
.tag-card dt { color: var(--muted); font-size: 12px; }
.tag-card dd { margin: 2px 0 0; font-weight: 700; }
.tag-card ul { margin: 8px 0 0; padding-left: 18px; }
.rule { color: #3f3f3f; font-size: 13px; }
.note { color: var(--warn); font-weight: 600; }
.tag-badge { display: inline-block; font-family: var(--mono); font-size: 12px; border-radius: 999px; padding: 3px 7px; border: 1px solid var(--line); background: #f4f4f1; }
.tag-badge.final { background: #e7f6f3; border-color: #9bd3cb; color: #064e45; }
.tag-badge.supporting { background: #f0eafb; border-color: #c4b5fd; color: #4c1d95; }
.tag-badge.status { background: #fff7ed; border-color: #fdba74; color: #9a3412; }
.filters { display: grid; grid-template-columns: minmax(220px, 1fr) repeat(4, minmax(120px, 180px)) auto auto; gap: 8px; align-items: center; margin-bottom: 10px; }
.filters input, .filters select { width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 7px; background: #fff; }
.filters label { font-size: 13px; white-space: nowrap; }
.table-note { color: var(--muted); margin: 8px 0; }
#recordsTable td:nth-child(4), #recordsTable td:nth-child(14) { max-width: 320px; overflow-wrap: anywhere; }
.queue-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.queue-block h3 { display: flex; justify-content: space-between; }
.queue-block ul { margin: 0; padding-left: 18px; }
.queue-block li { margin: 0 0 8px; font-size: 13px; }
.queue-block em { display: block; color: var(--muted); font-style: normal; font-family: var(--mono); }
.rep-group { margin-bottom: 18px; }
details { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; margin: 8px 0; }
summary { cursor: pointer; font-weight: 600; }
@media (max-width: 900px) {
  .filters { grid-template-columns: 1fr 1fr; }
  th { position: static; }
}
"""


JS = """
const data = JSON.parse(document.getElementById('dashboard-data').textContent);
const tbody = document.querySelector('#recordsTable tbody');
const recordCount = document.getElementById('recordCount');
const controls = ['searchInput','tagFilter','yearFilter','sectionFilter','confidenceFilter','hideHoldouts','needsOnly']
  .map(id => document.getElementById(id));

function cell(value) {
  const td = document.createElement('td');
  td.textContent = value == null ? '' : String(value);
  return td;
}

function matches(record) {
  const query = document.getElementById('searchInput').value.trim().toLowerCase();
  const tag = document.getElementById('tagFilter').value;
  const year = document.getElementById('yearFilter').value;
  const section = document.getElementById('sectionFilter').value;
  const confidence = document.getElementById('confidenceFilter').value;
  const tags = [record.provisional_tags.primary].concat(record.provisional_tags.secondary || []);
  if (query && !JSON.stringify(record).toLowerCase().includes(query)) return false;
  if (tag && !tags.includes(tag)) return false;
  if (year && String(record.year) !== year) return false;
  if (section && record.section !== section) return false;
  if (confidence && record.provisional_tags.confidence !== confidence) return false;
  if (document.getElementById('hideHoldouts').checked && record.holdout) return false;
  if (document.getElementById('needsOnly').checked && !record.needs_review) return false;
  return true;
}

function renderRows() {
  const rows = data.records.filter(matches);
  tbody.replaceChildren();
  for (const record of rows) {
    const tr = document.createElement('tr');
    [
      record.year, record.section, record.question_no, record.review_file,
      record.selected_choice, record.correct_choice, record.provisional_tags.primary,
      (record.provisional_tags.secondary || []).join(', '), record.provisional_tags.confidence,
      record.needs_review ? 'yes' : 'no', record.holdout ? 'yes' : 'no',
      record.use_for_tag_frequency ? 'yes' : 'no',
      record.use_for_final_tag_promotion ? 'yes' : 'no',
      record.tag_rationale
    ].forEach(value => tr.appendChild(cell(value)));
    tbody.appendChild(tr);
  }
  recordCount.textContent = `${rows.length} of ${data.records.length} records shown`;
}

controls.forEach(control => control.addEventListener('input', renderRows));
renderRows();
"""


def validate_html(output: str) -> None:
    if not output.strip():
        raise ValueError("Generated dashboard HTML is empty")
    missing = [section_id for section_id in SECTION_IDS if f'<section id="{section_id}"' not in output]
    if missing:
        raise ValueError(f"Generated dashboard missing section anchors: {missing}")


def main() -> None:
    records = load_records()
    metadata = classify_tags()
    audit = validate_records(records, metadata)
    stats = compute_counts(records, metadata)
    tag_frequency = compute_tag_frequency(records)
    output = build_dashboard_html(records, stats, metadata, tag_frequency, audit)
    validate_html(output)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output, encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "records": stats["total_records"],
                "active": stats["active_records"],
                "holdouts": stats["holdout_records"],
                "needs_review_non_holdout": stats["needs_review_non_holdout"],
                "output_path": OUTPUT_PATH.relative_to(ROOT).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
