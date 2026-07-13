from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote


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
NAV_LABELS = {
    "overview": "Overview",
    "tag-frequency": "Frequency",
    "final-tags": "Final Tags",
    "supporting-status-tags": "Support Tags",
    "year-section-breakdown": "Years",
    "records-table": "Records",
    "review-queue": "Queue",
    "representative-cases": "Cases",
    "audit": "Audit",
}


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
    for match in re.finditer(r"^#{2,3} `([^`]+)`\s*$", text, re.MULTILINE):
        tag_id = match.group(1)
        start = match.end()
        next_match = re.search(r"^#{2,3} `", text[start:], re.MULTILINE)
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
    records: list[dict[str, Any]], tag_id: str, limit: int | None = 4
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
    return active if limit is None else active[:limit]


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


def review_href(record: dict[str, Any]) -> str:
    return "/review?file=" + quote(str(record.get("review_file") or ""), safe="")


def review_label(record: dict[str, Any]) -> str:
    review_file = str(record.get("review_file") or "")
    path = PurePosixPath(review_file.replace("\\", "/"))
    qid = path.name.removesuffix(".review.json")
    if path.parent.name and qid:
        return f"{path.parent.name} {qid}"
    return f"{record.get('year')} {record.get('section')} q{int(record.get('question_no') or 0):02d}"


def render_review_file_link(record: dict[str, Any]) -> str:
    return f'<a class="review-link" href="{h(review_href(record))}">{h(review_label(record))}</a>'


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
    final_card_cases = {
        tag_id: select_representative_cases(records, tag_id, limit=None) for tag_id in FINAL_V1_TAGS
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
        f"<td><div class=\"frequency-cell\"><div class=\"frequency-track\" aria-hidden=\"true\"><span style=\"width: {min(float(row['primary_percent']) * 4, 100)}%\"></span></div><strong>{row['primary_percent']}%</strong></div></td>"
        "</tr>"
        for row in tag_frequency
    )

    final_cards = "\n".join(
        f"""
        <article class="tag-card">
          <header>{render_tag_badge(tag_id, metadata)}<span>{h(metadata[tag_id].get('korean'))}</span></header>
          <p class="tag-definition">{h(metadata[tag_id].get('definition'))}</p>
          <dl>
            <div><dt>Primary</dt><dd>{next((row['primary_count'] for row in tag_frequency if row['tag_id'] == tag_id), 0)}</dd></div>
            <div><dt>Primary + secondary</dt><dd>{next((row['all_count'] for row in tag_frequency if row['tag_id'] == tag_id), 0)}</dd></div>
          </dl>
          <p class="rule"><strong>Correction cue</strong>{h(metadata[tag_id].get('correction_rule'))}</p>
          <details class="case-list"><summary>Browse {len(final_card_cases[tag_id])} linked cases</summary><ul class="tag-card-cases">{''.join(f'<li>{render_review_file_link(case)}</li>' for case in final_card_cases[tag_id])}</ul></details>
        </article>
        """
        for tag_id in FINAL_V1_TAGS
    )

    support_cards = "\n".join(
        f"""
        <article class="tag-card supporting-card">
          <header>{render_tag_badge(tag_id, metadata)}<span>{h(metadata[tag_id].get('role'))}</span></header>
          <p class="tag-definition">{h(metadata[tag_id].get('definition'))}</p>
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
          <ul>{''.join(f'<li><strong>{render_record_link(record)}</strong> {render_review_file_link(record)} <em>{h(record["provisional_tags"]["primary"])}</em></li>' for record in items)}</ul>
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
    <div class="header-inner">
      <div class="brand-block"><span class="brand-mark">LP</span><div><p>LEET Practice / Analysis workspace</p><h1>Tagging Dashboard</h1></div></div>
      <a class="header-action" href="#review-queue"><span>{stats['needs_review_non_holdout']}</span> item ready for review</a>
    </div>
    <nav aria-label="Dashboard sections">{''.join(f'<a href="#{section_id}">{h(NAV_LABELS[section_id])}</a>' for section_id in SECTION_IDS)}</nav>
  </header>
  <main>
    <section id="overview">
      <div class="overview-intro">
        <div><p class="eyebrow">Dataset health</p><h2>Turn review evidence into reliable error patterns.</h2><p class="section-copy">Track the active corpus, focus the review queue, and compare mechanism frequency without losing the source evidence behind each tag.</p></div>
        <div class="priority-card"><span>Next action</span><strong>{stats['needs_review_non_holdout']} active record needs review</strong><a href="#review-queue">Open review queue <span aria-hidden="true">→</span></a></div>
      </div>
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
      <div class="section-heading"><div><p class="eyebrow">Pattern distribution</p><h2>Active Tag Frequency</h2></div><p>Based on <strong>{stats['active_records']}</strong> active records. Bars use a 25% comparison scale.</p></div>
      <div class="table-scroll"><table><caption class="sr-only">Active tag frequency across records used for analysis</caption><thead><tr><th scope="col">Tag</th><th scope="col">Role</th><th scope="col">Primary</th><th scope="col">Primary + secondary</th><th scope="col">% active primary</th></tr></thead><tbody>{frequency_rows}</tbody></table></div>
    </section>

    <section id="final-tags">
      <div class="section-heading"><div><p class="eyebrow">Mechanism library</p><h2>Final v1 Tags</h2></div><p>Definitions stay visible; linked evidence is disclosed on demand.</p></div>
      <div class="tag-grid">{final_cards}</div>
    </section>

    <section id="supporting-status-tags">
      <h2>Supporting and Status Tags</h2>
      <div class="tag-grid">{support_cards}</div>
    </section>

    <section id="year-section-breakdown">
      <h2>Year × Section Breakdown</h2>
      <div class="table-scroll"><table><caption class="sr-only">Active records and frequent tags by year and section</caption><thead><tr><th scope="col">Year</th><th scope="col">Section</th><th scope="col">Active records</th><th scope="col">Most frequent primary tags</th></tr></thead><tbody>{breakdown_rows}</tbody></table></div>
    </section>

    <section id="records-table">
      <div class="section-heading"><div><p class="eyebrow">Evidence explorer</p><h2>Records Table</h2></div><p>Combine filters to isolate the next useful review set.</p></div>
      <div class="filters">
        <label class="filter-field filter-search"><span>Search</span><input id="searchInput" type="search" placeholder="Question, tag, or rationale"></label>
        <label class="filter-field"><span>Tag</span><select id="tagFilter"><option value="">All tags</option>{''.join(f'<option>{h(tag)}</option>' for tag in all_tags)}</select></label>
        <label class="filter-field"><span>Year</span><select id="yearFilter"><option value="">All years</option>{''.join(f'<option>{h(year)}</option>' for year in years)}</select></label>
        <label class="filter-field"><span>Section</span><select id="sectionFilter"><option value="">All sections</option>{''.join(f'<option>{h(section)}</option>' for section in sections)}</select></label>
        <label class="filter-field"><span>Confidence</span><select id="confidenceFilter"><option value="">All levels</option>{''.join(f'<option>{h(conf)}</option>' for conf in confidences)}</select></label>
        <label class="filter-field"><span>Retry status</span><select id="retryStatusFilter" disabled><option value="">All retry states</option><option value="never">Never retried</option><option value="correct">Latest correct</option><option value="incorrect">Latest incorrect</option><option value="skipped">Latest skipped</option></select></label>
        <div class="filter-toggles">
        <label><input id="hideHoldouts" type="checkbox"> Hide holdouts</label>
        <label><input id="needsOnly" type="checkbox"> Needs-review only</label>
        </div>
        <button id="resetFilters" type="button">Reset</button>
      </div>
      <div class="retry-builder" aria-labelledby="retryBuilderTitle">
        <div class="retry-builder-copy">
          <p class="eyebrow">Focused practice</p>
          <h3 id="retryBuilderTitle">Build a retry PDF</h3>
          <p>Recommend a balanced set from the currently filtered mistakes, then adjust it with the row checkboxes.</p>
        </div>
        <label class="retry-field"><span>Title</span><input id="retryTitle" type="text" maxlength="160" value="LEET 오답 재풀이"></label>
        <label class="retry-field retry-limit"><span>Recommendation size</span><input id="retryLimit" type="number" min="1" max="100" value="20"></label>
        <label class="retry-check"><input id="includeHoldouts" type="checkbox"> Include holdouts</label>
        <label class="retry-check"><input id="includeCompleted" type="checkbox"> Include completed</label>
        <div class="retry-actions">
          <button id="recommendSelection" class="primary-action" type="button">추천 선택</button>
          <button id="selectVisible" type="button">Select all shown</button>
          <button id="clearSelection" type="button">Clear</button>
        </div>
        <div class="retry-generate">
          <strong id="selectedCount" aria-live="polite">0 selected</strong>
          <button id="generateRetryPdf" class="primary-action" type="button" disabled>Generate retry PDF</button>
        </div>
        <div id="retryStatus" class="retry-status" aria-live="polite"></div>
      </div>
      <div class="table-note"><span id="recordCount"></span><span class="scroll-hint"> Scroll sideways for tags and rationale.</span></div>
      <div class="table-scroll records-scroll">
        <table id="recordsTable">
          <caption class="sr-only">Filterable tagging evidence records</caption>
          <thead><tr><th scope="col"><span class="sr-only">PDF selection</span></th><th scope="col">Year</th><th scope="col">Section</th><th scope="col">Q</th><th scope="col">Review file</th><th scope="col">Selected</th><th scope="col">Correct</th><th scope="col">Primary tag</th><th scope="col">Secondary</th><th scope="col">Confidence</th><th scope="col">Needs review</th><th scope="col">Holdout</th><th scope="col">Use frequency</th><th scope="col">Use promotion</th><th scope="col">Retry</th><th scope="col">Rationale</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
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
      <div class="table-scroll"><table><caption class="sr-only">Data integrity audit checks and results</caption><tbody>{audit_rows}</tbody></table></div>
    </section>
  </main>
  <script id="dashboard-data" type="application/json">{html.escape(json.dumps(dashboard_data, ensure_ascii=False), quote=False)}</script>
  <script>{JS}</script>
</body>
</html>
"""


def build_dashboard_data() -> dict[str, Any]:
    records = load_records()
    metadata = classify_tags()
    audit = validate_records(records, metadata)
    stats = compute_counts(records, metadata)
    tag_frequency = compute_tag_frequency(records)
    return {
        "records": records,
        "metadata": metadata,
        "stats": stats,
        "tagFrequency": tag_frequency,
        "audit": audit,
    }


def build_current_dashboard_html() -> str:
    dashboard_data = build_dashboard_data()
    return build_dashboard_html(
        dashboard_data["records"],
        dashboard_data["stats"],
        dashboard_data["metadata"],
        dashboard_data["tagFrequency"],
        dashboard_data["audit"],
    )


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
      <summary>{h(summary)} - {h(review_label(record))}</summary>
      <p>{render_review_file_link(record)}</p>
      <p><strong>Rationale:</strong> {h(record.get('tag_rationale'))}</p>
      <p><strong>User self-diagnosis:</strong> {h(review.get('user_self_diagnosis_summary'))}</p>
      <p><strong>Assistant feedback:</strong> {h(review.get('assistant_feedback_summary'))}</p>
      <p><strong>Canonical basis:</strong> {h(canonical.get('question_summary'))} {h(canonical.get('key_evidence_pointer'))}</p>
    </details>
    """


CSS = """
:root {
  --bg: #f4f6fb;
  --panel: #ffffff;
  --text: #172033;
  --muted: #667085;
  --line: #dfe4ee;
  --line-strong: #cbd3e1;
  --accent: #4f46e5;
  --accent-dark: #3730a3;
  --accent-soft: #eef2ff;
  --accent-2: #0891b2;
  --warn: #b45309;
  --danger: #b91c1c;
  --shadow: 0 10px 28px rgba(25, 37, 65, 0.07);
  --mono: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
body { margin: 0; background: var(--bg); color: var(--text); }
.app-header { position: sticky; top: 0; z-index: 5; background: rgba(255,255,255,.94); border-bottom: 1px solid var(--line); padding: 15px 24px 10px; backdrop-filter: blur(14px); box-shadow: 0 4px 18px rgba(25,37,65,.04); }
.header-inner { max-width: 1420px; margin: 0 auto 12px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.brand-block { display: flex; align-items: center; gap: 11px; }
.brand-mark { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 11px; color: #fff; background: linear-gradient(145deg, var(--accent), var(--accent-2)); font-size: 13px; font-weight: 800; letter-spacing: .04em; box-shadow: 0 8px 18px rgba(79,70,229,.24); }
.brand-block p { margin: 0 0 2px; color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
.app-header h1 { margin: 0; font-size: 21px; letter-spacing: -.02em; }
.header-action { display: inline-flex; align-items: center; gap: 8px; color: var(--accent-dark); text-decoration: none; font-size: 13px; font-weight: 700; background: var(--accent-soft); border: 1px solid #c7d2fe; border-radius: 999px; padding: 7px 12px 7px 8px; }
.header-action > span { display: grid; place-items: center; width: 22px; height: 22px; color: #fff; background: var(--accent); border-radius: 50%; }
nav { max-width: 1420px; margin: 0 auto; display: flex; gap: 6px; overflow-x: auto; scrollbar-width: thin; }
nav a { flex: 0 0 auto; color: var(--muted); text-decoration: none; font-size: 12px; font-weight: 650; padding: 6px 9px; border-radius: 7px; }
nav a:hover, nav a:focus-visible { color: var(--accent-dark); background: var(--accent-soft); outline: none; }
a { color: var(--accent); }
.review-link { font-family: var(--mono); overflow-wrap: anywhere; }
main { max-width: 1470px; margin: 0 auto; padding: 34px 24px 64px; }
section { margin: 0 0 42px; scroll-margin-top: 132px; }
h2 { font-size: 21px; margin: 0; letter-spacing: -.02em; }
h3 { font-size: 15px; margin: 0 0 10px; }
p { line-height: 1.45; }
code { font-family: var(--mono); background: #eef1f6; padding: 1px 4px; border-radius: 4px; }
.eyebrow { margin: 0 0 7px; color: var(--accent); font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.overview-intro { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 360px); gap: 22px; align-items: end; margin-bottom: 18px; }
.overview-intro h2 { max-width: 760px; font-size: clamp(28px, 3.5vw, 44px); line-height: 1.06; letter-spacing: -.045em; }
.section-copy { max-width: 760px; margin: 14px 0 0; color: var(--muted); font-size: 15px; }
.priority-card { display: grid; gap: 7px; padding: 18px; color: #fff; border-radius: 16px; background: linear-gradient(135deg, #312e81, #4f46e5 60%, #0e7490); box-shadow: 0 16px 32px rgba(49,46,129,.2); }
.priority-card > span { color: #c7d2fe; font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.priority-card strong { font-size: 18px; line-height: 1.3; }
.priority-card a { color: #fff; font-size: 13px; font-weight: 750; text-decoration: none; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 22px; margin-bottom: 14px; }
.section-heading > p { max-width: 480px; margin: 0; color: var(--muted); font-size: 13px; text-align: right; }
.metrics { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 10px; }
.metric, .tag-card, .queue-block { background: var(--panel); border: 1px solid var(--line); border-radius: 13px; padding: 15px; box-shadow: var(--shadow); }
.metric { min-height: 112px; position: relative; overflow: hidden; }
.metric::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: linear-gradient(var(--accent), var(--accent-2)); opacity: .8; }
.metric span { display: block; min-height: 38px; color: var(--muted); font-size: 11px; line-height: 1.35; }
.metric strong { display: block; font-size: 29px; margin-top: 7px; letter-spacing: -.035em; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); }
th, td { border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; font-size: 12px; }
th { position: sticky; top: 0; z-index: 1; background: #f7f8fb; color: #475467; font-size: 11px; letter-spacing: .03em; text-transform: uppercase; }
tbody tr:hover { background: #f8f9ff; }
.table-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); box-shadow: var(--shadow); }
.table-scroll table { border: 0; min-width: 720px; }
.records-scroll table { min-width: 1260px; }
.frequency-cell { display: grid; grid-template-columns: minmax(90px, 1fr) 48px; align-items: center; gap: 10px; min-width: 180px; }
.frequency-track { height: 7px; overflow: hidden; background: #e8ecf4; border-radius: 999px; }
.frequency-track span { display: block; height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-2)); border-radius: inherit; }
.frequency-cell strong { text-align: right; font-size: 12px; }
.tag-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 14px; }
.tag-card header { display: grid; gap: 6px; min-height: 48px; margin-bottom: 8px; }
.tag-card header span:not(.tag-badge) { font-weight: 700; line-height: 1.25; }
.tag-card p { margin: 8px 0; }
.tag-definition { min-height: 94px; color: #344054; }
.tag-card dl { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0; }
.tag-card dl div { background: #f7f8fb; border: 1px solid #edf0f5; border-radius: 9px; padding: 9px; }
.tag-card dt { color: var(--muted); font-size: 12px; }
.tag-card dd { margin: 2px 0 0; font-weight: 700; }
.tag-card ul { margin: 8px 0 0; padding-left: 18px; }
.tag-card-cases { max-height: 168px; overflow-y: auto; padding-right: 6px; }
.tag-card-cases li { margin-bottom: 5px; }
.rule { display: grid; gap: 4px; min-height: 74px; color: #344054; font-size: 13px; padding: 10px; background: var(--accent-soft); border-radius: 9px; }
.rule strong { color: var(--accent-dark); font-size: 10px; letter-spacing: .08em; text-transform: uppercase; }
.case-list { margin-top: 11px; padding: 0; border: 0; background: transparent; }
.case-list summary { color: var(--accent-dark); font-size: 12px; }
.note { color: var(--warn); font-weight: 600; }
.tag-badge { display: inline-block; width: fit-content; font-family: var(--mono); font-size: 11px; border-radius: 999px; padding: 4px 8px; border: 1px solid var(--line); background: #f4f5f8; }
.tag-badge.final { background: #ecfeff; border-color: #a5f3fc; color: #155e75; }
.tag-badge.supporting { background: #f0eafb; border-color: #c4b5fd; color: #4c1d95; }
.tag-badge.status { background: #fff7ed; border-color: #fdba74; color: #9a3412; }
.filters { display: grid; grid-template-columns: minmax(220px, 1.35fr) repeat(4, minmax(115px, .72fr)) auto auto; gap: 10px; align-items: end; padding: 14px; margin-bottom: 10px; background: var(--panel); border: 1px solid var(--line); border-radius: 13px; box-shadow: var(--shadow); }
.filter-field { display: grid !important; gap: 5px !important; }
.filter-field > span { color: var(--muted); font-size: 10px; font-weight: 750; letter-spacing: .07em; text-transform: uppercase; }
.filters input, .filters select { width: 100%; height: 38px; border: 1px solid var(--line-strong); border-radius: 8px; padding: 7px 9px; background: #fff; color: var(--text); }
.filters input:focus, .filters select:focus { border-color: var(--accent); outline: 3px solid rgba(79,70,229,.11); }
.filters label { display: flex; align-items: center; gap: 6px; font-size: 12px; white-space: nowrap; }
.filters label input { width: auto; height: auto; accent-color: var(--accent); }
.filter-toggles { display: grid; gap: 7px; padding-bottom: 2px; }
.filters button { height: 38px; border: 1px solid var(--line-strong); border-radius: 8px; padding: 0 13px; color: #344054; background: #fff; font-weight: 700; cursor: pointer; }
.filters button:hover { border-color: var(--accent); color: var(--accent-dark); }
.retry-builder { display: grid; grid-template-columns: minmax(220px, 1.25fr) minmax(230px, 1fr) 150px auto; gap: 14px; align-items: end; margin: 12px 0; padding: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: 13px; box-shadow: var(--shadow); }
.retry-builder-copy { align-self: center; }
.retry-builder-copy h3 { margin: 0; font-size: 17px; }
.retry-builder-copy p:last-child { margin: 6px 0 0; color: var(--muted); font-size: 12px; }
.retry-field { display: grid; gap: 5px; }
.retry-field > span { color: var(--muted); font-size: 10px; font-weight: 750; letter-spacing: .07em; text-transform: uppercase; }
.retry-field input { width: 100%; height: 38px; border: 1px solid var(--line-strong); border-radius: 8px; padding: 7px 9px; color: var(--text); background: #fff; }
.retry-field input:focus { border-color: var(--accent); outline: 3px solid rgba(79,70,229,.11); }
.retry-check { display: flex; align-items: center; gap: 7px; min-height: 38px; font-size: 12px; }
.retry-check input, .row-selector { accent-color: var(--accent); }
.retry-actions { grid-column: 2 / -1; display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.retry-actions button, .retry-generate button { min-height: 38px; border: 1px solid var(--line-strong); border-radius: 8px; padding: 7px 12px; color: #344054; background: #fff; font-weight: 700; cursor: pointer; }
.retry-actions button:hover, .retry-generate button:hover { border-color: var(--accent); color: var(--accent-dark); }
.retry-actions .primary-action, .retry-generate .primary-action { color: #fff; border-color: var(--accent); background: var(--accent); }
.retry-actions .primary-action:hover, .retry-generate .primary-action:hover { color: #fff; border-color: var(--accent-dark); background: var(--accent-dark); }
.retry-generate { grid-column: 1 / -1; display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
.retry-generate strong { color: var(--accent-dark); font-size: 13px; }
.retry-generate button:disabled { cursor: not-allowed; opacity: .5; }
.retry-status { grid-column: 1 / -1; min-height: 0; color: var(--muted); font-size: 12px; text-align: right; }
.retry-status:empty { display: none; }
.retry-status.error { color: var(--danger); }
.retry-status.success { color: #047857; }
.retry-status a { font-weight: 750; }
.retry-badge { display: inline-flex; border-radius: 999px; padding: 4px 8px; color: var(--muted); background: #f2f4f7; white-space: nowrap; }
.retry-badge.correct { color: #047857; background: #ecfdf3; }
.retry-badge.incorrect { color: #b42318; background: #fef3f2; }
.retry-badge.skipped { color: #b54708; background: #fffaeb; }
.row-selector { width: 16px; height: 16px; cursor: pointer; }
.selected-row { background: var(--accent-soft); }
.table-note { color: var(--muted); margin: 8px 0; }
.scroll-hint { display: none; }
#recordsTable td:nth-child(5) { max-width: 220px; overflow-wrap: anywhere; }
#recordsTable td:nth-child(8), #recordsTable td:nth-child(9) { font-family: var(--mono); font-size: 12px; }
#recordsTable td:nth-child(15) { width: 280px; max-width: 280px; }
.rationale-summary { cursor: pointer; color: var(--accent); font-weight: 600; }
.rationale-details[open] .rationale-summary { margin-bottom: 6px; }
.rationale-text { color: var(--text); line-height: 1.38; max-height: 170px; overflow: auto; padding-right: 4px; }
.empty-row td { padding: 34px 18px; color: var(--muted); text-align: center; font-size: 13px; }
.queue-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.queue-block h3 { display: flex; justify-content: space-between; color: #344054; }
.queue-block h3 span { display: grid; place-items: center; min-width: 24px; height: 24px; padding: 0 7px; color: var(--accent-dark); background: var(--accent-soft); border-radius: 999px; }
.queue-block ul { margin: 0; padding-left: 18px; }
.queue-block li { margin: 0 0 8px; font-size: 13px; }
.queue-block em { display: block; color: var(--muted); font-style: normal; font-family: var(--mono); }
.rep-group { margin-bottom: 18px; }
details { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 11px 13px; margin: 8px 0; }
summary { cursor: pointer; font-weight: 600; }
@media (max-width: 1180px) {
  .metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .filter-search { grid-column: span 2; }
  .retry-builder { grid-template-columns: 1fr 1fr; }
  .retry-actions { grid-column: 1 / -1; }
}
@media (max-width: 900px) {
  .overview-intro { grid-template-columns: 1fr; align-items: stretch; }
  .metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .section-heading { align-items: start; flex-direction: column; gap: 5px; }
  .section-heading > p { text-align: left; }
  .filters { grid-template-columns: 1fr 1fr; }
  .filter-search { grid-column: span 2; }
}
@media (max-width: 700px) {
  .app-header { padding: 14px 16px 12px; }
  .app-header h1 { font-size: 19px; }
  .brand-block p, .header-action { display: none; }
  nav { padding-bottom: 2px; }
  main { padding: 26px 16px 44px; }
  section { margin-bottom: 34px; scroll-margin-top: 108px; }
  .overview-intro h2 { font-size: 31px; }
  .metrics { grid-template-columns: 1fr 1fr; gap: 8px; }
  .metric { min-height: 92px; padding: 12px; }
  .metric span { min-height: 32px; font-size: 11px; }
  .metric strong { font-size: 26px; }
  .tag-grid, .queue-grid { grid-template-columns: 1fr; }
  .filters { grid-template-columns: 1fr; }
  .filter-search { grid-column: auto; }
  .filters label { justify-content: flex-start; white-space: normal; }
  .retry-builder { grid-template-columns: 1fr; }
  .retry-actions, .retry-generate, .retry-status { grid-column: auto; justify-content: flex-start; text-align: left; }
  .scroll-hint { display: inline; }
}
"""


JS = """
const data = JSON.parse(document.getElementById('dashboard-data').textContent);
const tbody = document.querySelector('#recordsTable tbody');
const recordCount = document.getElementById('recordCount');
const controls = ['searchInput','tagFilter','yearFilter','sectionFilter','confidenceFilter','retryStatusFilter','hideHoldouts','needsOnly']
  .map(id => document.getElementById(id));
const selectedFiles = new Set();
const confidenceOrder = {high: 0, medium: 1, low: 2};
let retryStatusesLoaded = false;

function cell(value) {
  const td = document.createElement('td');
  td.textContent = value == null ? '' : String(value);
  return td;
}

function linkCell(label, href) {
  const td = document.createElement('td');
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.textContent = label == null ? '' : String(label);
  anchor.className = 'review-link';
  td.appendChild(anchor);
  return td;
}

function rationaleCell(value) {
  const td = document.createElement('td');
  const details = document.createElement('details');
  details.className = 'rationale-details';
  const summary = document.createElement('summary');
  summary.className = 'rationale-summary';
  summary.textContent = 'Read rationale';
  const text = document.createElement('div');
  text.className = 'rationale-text';
  text.textContent = value == null ? '' : String(value);
  details.append(summary, text);
  td.appendChild(details);
  return td;
}

function retryOutcome(record) {
  if (!retryStatusesLoaded) return 'unknown';
  return record.retry_status ? record.retry_status.latest_outcome : 'never';
}

function retryStatusCell(record) {
  const td = document.createElement('td');
  const badge = document.createElement('span');
  const outcome = retryOutcome(record);
  badge.className = `retry-badge ${outcome}`;
  if (outcome === 'unknown') badge.textContent = 'Loading';
  else if (outcome === 'never') badge.textContent = 'Never';
  else {
    const attempts = record.retry_status.attempt_count;
    badge.textContent = `${outcome} · ${attempts} ${attempts === 1 ? 'try' : 'tries'}`;
    badge.title = `Last saved ${record.retry_status.last_answered_at}`;
  }
  td.appendChild(badge);
  return td;
}

function selectorCell(record) {
  const td = document.createElement('td');
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.className = 'row-selector';
  input.checked = selectedFiles.has(record.review_file);
  input.disabled = !isRetryEligible(record);
  if (input.disabled) {
    input.title = record.holdout
      ? 'Enable Include holdouts to select this record.'
      : 'Enable Include completed to select a latest-correct record.';
  }
  input.setAttribute('aria-label', `Select ${reviewLabel(record)} for retry PDF`);
  input.addEventListener('change', () => {
    if (input.checked) selectedFiles.add(record.review_file);
    else selectedFiles.delete(record.review_file);
    updateSelectionUi();
  });
  td.appendChild(input);
  return td;
}

function reviewHref(record) {
  return `/review?file=${encodeURIComponent(record.review_file)}`;
}

function reviewLabel(record) {
  const parts = String(record.review_file || '').split('/');
  const filename = parts.pop() || '';
  const parent = parts.pop() || '';
  const qid = filename.replace(/\\.review\\.json$/, '');
  if (parent && qid) return `${parent} ${qid}`;
  const qno = String(record.question_no || 0).padStart(2, '0');
  return `${record.year} ${record.section} q${qno}`;
}

function matches(record) {
  const query = document.getElementById('searchInput').value.trim().toLowerCase();
  const tag = document.getElementById('tagFilter').value;
  const year = document.getElementById('yearFilter').value;
  const section = document.getElementById('sectionFilter').value;
  const confidence = document.getElementById('confidenceFilter').value;
  const retryStatus = document.getElementById('retryStatusFilter').value;
  const tags = [record.provisional_tags.primary].concat(record.provisional_tags.secondary || []);
  if (query && !JSON.stringify(record).toLowerCase().includes(query)) return false;
  if (tag && !tags.includes(tag)) return false;
  if (year && String(record.year) !== year) return false;
  if (section && record.section !== section) return false;
  if (confidence && record.provisional_tags.confidence !== confidence) return false;
  if (retryStatus && retryOutcome(record) !== retryStatus) return false;
  if (document.getElementById('hideHoldouts').checked && record.holdout) return false;
  if (document.getElementById('needsOnly').checked && !record.needs_review) return false;
  return true;
}

function filteredRecords() {
  return data.records.filter(matches);
}

function isRetryEligible(record) {
  const baseEligible = Boolean(record.use_for_tag_frequency) ||
    (document.getElementById('includeHoldouts').checked && Boolean(record.holdout));
  if (!baseEligible) return false;
  return retryOutcome(record) !== 'correct' || document.getElementById('includeCompleted').checked;
}

function retryLimit() {
  const field = document.getElementById('retryLimit');
  const parsed = Number.parseInt(field.value, 10);
  const value = Number.isFinite(parsed) ? Math.min(100, Math.max(1, parsed)) : 20;
  field.value = String(value);
  return value;
}

function compareRetryRecords(left, right) {
  const leftConfidence = confidenceOrder[left.provisional_tags.confidence] ?? 9;
  const rightConfidence = confidenceOrder[right.provisional_tags.confidence] ?? 9;
  if (leftConfidence !== rightConfidence) return leftConfidence - rightConfidence;
  return [left.year, left.section, left.question_no, left.review_file]
    .map(String).join('|').localeCompare(
      [right.year, right.section, right.question_no, right.review_file].map(String).join('|'),
      'ko',
      {numeric: true}
    );
}

function balancedRecommendation(records, limit) {
  const groups = new Map();
  for (const record of records) {
    const tag = record.provisional_tags.primary;
    if (!groups.has(tag)) groups.set(tag, []);
    groups.get(tag).push(record);
  }
  const queues = Array.from(groups.entries())
    .map(([tag, items]) => ({tag, total: items.length, items: items.sort(compareRetryRecords)}))
    .sort((left, right) => right.total - left.total || left.tag.localeCompare(right.tag));
  const recommendation = [];
  while (recommendation.length < limit && queues.some(group => group.items.length)) {
    for (const group of queues) {
      if (recommendation.length >= limit) break;
      const record = group.items.shift();
      if (record) recommendation.push(record);
    }
  }
  return recommendation;
}

function retryTier(record) {
  const outcome = retryOutcome(record);
  if (outcome === 'incorrect') return 0;
  if (outcome === 'skipped') return 1;
  if (outcome === 'correct') return 3;
  return 2;
}

function recommendRecords(records, limit) {
  const eligible = records.filter(isRetryEligible);
  const tiers = document.getElementById('includeCompleted').checked ? [0, 1, 2, 3] : [0, 1, 2];
  const recommendation = [];
  for (const tier of tiers) {
    const remaining = limit - recommendation.length;
    if (remaining <= 0) break;
    recommendation.push(...balancedRecommendation(eligible.filter(record => retryTier(record) === tier), remaining));
  }
  return recommendation;
}

function updateSelectionUi() {
  const count = selectedFiles.size;
  document.getElementById('selectedCount').textContent = `${count} selected`;
  document.getElementById('generateRetryPdf').disabled = count === 0;
  document.querySelectorAll('.row-selector').forEach(input => {
    const row = input.closest('tr');
    row.classList.toggle('selected-row', input.checked);
  });
}

function setRetryStatus(message, kind = '') {
  const status = document.getElementById('retryStatus');
  status.className = `retry-status ${kind}`.trim();
  status.textContent = message;
}

function renderRows() {
  const rows = filteredRecords();
  tbody.replaceChildren();
  for (const record of rows) {
    const tr = document.createElement('tr');
    tr.appendChild(selectorCell(record));
    [
      record.year, record.section, record.question_no
    ].forEach(value => tr.appendChild(cell(value)));
    tr.appendChild(linkCell(reviewLabel(record), reviewHref(record)));
    [
      record.selected_choice, record.correct_choice, record.provisional_tags.primary,
      (record.provisional_tags.secondary || []).join(', '), record.provisional_tags.confidence,
      record.needs_review ? 'yes' : 'no', record.holdout ? 'yes' : 'no',
      record.use_for_tag_frequency ? 'yes' : 'no',
      record.use_for_final_tag_promotion ? 'yes' : 'no'
    ].forEach(value => tr.appendChild(cell(value)));
    tr.appendChild(retryStatusCell(record));
    tr.appendChild(rationaleCell(record.tag_rationale));
    tbody.appendChild(tr);
  }
  if (!rows.length) {
    const tr = document.createElement('tr');
    tr.className = 'empty-row';
    const td = document.createElement('td');
    td.colSpan = 16;
    td.textContent = 'No records match these filters. Reset or broaden the search.';
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
  recordCount.textContent = `${rows.length} of ${data.records.length} records shown`;
  updateSelectionUi();
}

controls.forEach(control => control.addEventListener('input', renderRows));
document.getElementById('resetFilters').addEventListener('click', () => {
  controls.forEach(control => {
    if (control.type === 'checkbox') control.checked = false;
    else control.value = '';
  });
  renderRows();
  document.getElementById('searchInput').focus();
});
document.getElementById('recommendSelection').addEventListener('click', () => {
  const recommendation = recommendRecords(filteredRecords(), retryLimit());
  selectedFiles.clear();
  recommendation.forEach(record => selectedFiles.add(record.review_file));
  renderRows();
  setRetryStatus(
    recommendation.length
      ? `${recommendation.length} questions recommended across primary error tags.`
      : 'No eligible records match the current filters.',
    recommendation.length ? '' : 'error'
  );
});
document.getElementById('selectVisible').addEventListener('click', () => {
  filteredRecords().filter(isRetryEligible).forEach(record => selectedFiles.add(record.review_file));
  renderRows();
  setRetryStatus('All eligible records currently shown were selected.');
});
document.getElementById('clearSelection').addEventListener('click', () => {
  selectedFiles.clear();
  renderRows();
  setRetryStatus('Selection cleared.');
});
document.getElementById('includeHoldouts').addEventListener('change', event => {
  if (!event.target.checked) {
    const holdoutFiles = new Set(data.records.filter(record => record.holdout).map(record => record.review_file));
    holdoutFiles.forEach(reviewFile => selectedFiles.delete(reviewFile));
  }
  renderRows();
});
document.getElementById('includeCompleted').addEventListener('change', event => {
  if (!event.target.checked) {
    data.records
      .filter(record => retryOutcome(record) === 'correct')
      .forEach(record => selectedFiles.delete(record.review_file));
  }
  renderRows();
});
document.getElementById('generateRetryPdf').addEventListener('click', async () => {
  if (!selectedFiles.size) return;
  const button = document.getElementById('generateRetryPdf');
  const title = document.getElementById('retryTitle').value.trim() || 'LEET 오답 재풀이';
  button.disabled = true;
  setRetryStatus('Generating PDF...');
  try {
    const response = await fetch('/api/retry-pdf', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        review_files: Array.from(selectedFiles),
        limit: selectedFiles.size,
        include_holdout: document.getElementById('includeHoldouts').checked,
        include_completed: document.getElementById('includeCompleted').checked,
        title
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || result.error || 'PDF generation failed.');
    const status = document.getElementById('retryStatus');
    status.className = 'retry-status success';
    status.replaceChildren(document.createTextNode(`Created ${result.selected_count} questions. `));
    for (const [label, href] of [['Download PDF', result.pdf_url], ['결과 입력', result.result_entry_url], ['Manifest', result.manifest_url]]) {
      if (!href) continue;
      const link = document.createElement('a');
      link.href = href;
      link.textContent = label;
      status.append(link, document.createTextNode(' '));
    }
  } catch (error) {
    setRetryStatus(error.message || String(error), 'error');
  } finally {
    button.disabled = selectedFiles.size === 0;
  }
});
renderRows();
fetch('/api/retry-statuses')
  .then(response => response.ok ? response.json() : Promise.reject(new Error('Retry status unavailable')))
  .then(result => {
    const statuses = result.by_review_file || {};
    data.records.forEach(record => { record.retry_status = statuses[record.review_file] || null; });
    retryStatusesLoaded = true;
    document.getElementById('retryStatusFilter').disabled = false;
    renderRows();
  })
  .catch(error => {
    document.getElementById('retryStatusFilter').disabled = true;
    setRetryStatus(error.message || String(error), 'error');
  });
"""


def validate_html(output: str) -> None:
    if not output.strip():
        raise ValueError("Generated dashboard HTML is empty")
    missing = [section_id for section_id in SECTION_IDS if f'<section id="{section_id}"' not in output]
    if missing:
        raise ValueError(f"Generated dashboard missing section anchors: {missing}")


def normalize_html_output(output: str) -> str:
    return "\n".join(line.rstrip() for line in output.splitlines()) + "\n"


def main() -> None:
    dashboard_data = build_dashboard_data()
    stats = dashboard_data["stats"]
    output = build_dashboard_html(
        dashboard_data["records"],
        stats,
        dashboard_data["metadata"],
        dashboard_data["tagFrequency"],
        dashboard_data["audit"],
    )
    output = normalize_html_output(output)
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
