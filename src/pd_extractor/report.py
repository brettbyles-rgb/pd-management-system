from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from urllib.parse import quote


def _h(value: object) -> str:
    return html.escape(str(value or ""))


def _rows(items: list[dict], columns: list[tuple[str, str]]) -> str:
    if not items:
        return '<p class="empty">None extracted</p>'
    head = "".join(f"<th>{_h(label)}</th>" for _, label in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_h(item.get(key, ''))}</td>" for key, _ in columns) + "</tr>"
        for item in items
    )
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _list(items: list[dict]) -> str:
    if not items:
        return '<p class="empty">None extracted</p>'
    return "<ol>" + "".join(f"<li>{_h(item.get('text', ''))}</li>" for item in items) + "</ol>"


def _section(title: str, content: str, open_by_default: bool = False) -> str:
    opened = " open" if open_by_default else ""
    return f"<details{opened}><summary>{_h(title)}</summary><div class=\"section-body\">{content}</div></details>"


def _document_card(data: dict, json_name: str, sample_dir: Path, report_path: Path) -> str:
    record = data["pd_record"]
    filename = record["source_filename"]
    slug = Path(filename).stem
    source_href = quote((Path("..") / sample_dir.name / filename).as_posix())
    json_href = quote((Path("batch") / json_name).as_posix())
    issues = data.get("extraction_issues", [])
    status_class = (
        "ok" if record["extraction_status"] == "Extraction complete"
        else "warning" if record["extraction_status"] == "Extraction complete with warnings"
        else "review"
    )

    raw_fields = data["role_description_fields"].get("raw_fields", [])
    metadata = _rows(raw_fields, [("field_name", "Field"), ("field_value", "Value")])
    sections = data.get("sections", {})
    long_sections = "".join(
        f"<h4>{_h(label)}</h4><p class=\"prose\">{_h(sections.get(key, '')) or '<span class=empty>Not extracted</span>'}</p>"
        for key, label in [
            ("primary_purpose", "Primary purpose"), ("decision_making", "Decision making"),
            ("reporting_line", "Reporting line"), ("direct_reports", "Direct reports"),
            ("budget_expenditure", "Budget/Expenditure"),
        ]
    )
    relationships = _rows(data.get("key_relationships", []), [
        ("relationship_group", "Group"), ("who", "Who"), ("why", "Why")
    ])
    capabilities = _rows(data.get("capabilities", []), [
        ("capability_type", "Type"), ("framework", "Framework"),
        ("capability_name", "Capability"), ("level", "Level")
    ])
    issue_html = _rows(issues, [
        ("severity", "Severity"), ("field_or_section", "Area"), ("description", "Issue")
    ]) if issues else '<p class="ok-text">No extraction issues recorded.</p>'

    stats = [
        ("Accountabilities", len(data.get("key_accountabilities", []))),
        ("Challenges", len(data.get("key_challenges", []))),
        ("Relationships", len(data.get("key_relationships", []))),
        ("Requirements", len(data.get("essential_requirements", []))),
        ("Capabilities", len(data.get("capabilities", []))),
    ]
    stats_html = "".join(f'<span class="stat"><b>{count}</b>{_h(label)}</span>' for label, count in stats)

    return f"""
    <article id="{_h(slug)}" class="document-card">
      <header class="doc-header">
        <div><span class="status {status_class}">{_h(record['extraction_status'])}</span>
        <h2>{_h(record['role_title'])}</h2><p class="filename">{_h(filename)}</p></div>
        <div class="actions"><a href="{source_href}">Open Word source</a><a href="{json_href}">Open JSON</a></div>
      </header>
      <div class="stats">{stats_html}</div>
      {_section('Review issues', issue_html, bool(issues))}
      {_section('Role description fields', metadata, True)}
      {_section('Main sections', long_sections)}
      {_section('Key accountabilities', _list(data.get('key_accountabilities', [])))}
      {_section('Key challenges', _list(data.get('key_challenges', [])))}
      {_section('Key relationships', relationships, True)}
      {_section('Key Knowledge and Experience', _list(data.get('key_knowledge_and_experience', [])))}
      {_section('Essential requirements', _list(data.get('essential_requirements', [])))}
      {_section('Capabilities', capabilities, True)}
    </article>"""


def generate_validation_report(json_dir: Path, sample_dir: Path, report_path: Path) -> Path:
    files = sorted(path for path in json_dir.glob("*.json") if path.name != "_summary.json")
    documents = [(path, json.loads(path.read_text(encoding="utf-8-sig"))) for path in files]
    cards = "".join(_document_card(data, path.name, sample_dir, report_path) for path, data in documents)
    nav = "".join(
        f'<a href="#{_h(Path(data["pd_record"]["source_filename"]).stem)}">{_h(data["pd_record"]["role_title"])}</a>'
        for _, data in documents
    )
    complete = sum(
        data["pd_record"]["extraction_status"] in {"Extraction complete", "Extraction complete with warnings"}
        for _, data in documents
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PD Extractor Validation Report</title>
<style>
:root{{--ink:#172033;--muted:#667085;--line:#d9deea;--paper:#fff;--bg:#f3f5f9;--purple:#481579;--green:#16794d;--amber:#9a5a00}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,sans-serif}}
.layout{{display:grid;grid-template-columns:280px minmax(0,1fr);min-height:100vh}} aside{{position:sticky;top:0;height:100vh;overflow:auto;background:#211238;color:white;padding:28px 20px}}
aside h1{{font-size:20px;margin:0 0 6px}} aside p{{color:#d8cde6;margin:0 0 22px}} nav{{display:grid;gap:5px}} nav a{{color:white;text-decoration:none;padding:8px 10px;border-radius:7px}} nav a:hover{{background:#ffffff1a}}
main{{padding:32px;max-width:1250px;width:100%}} .report-summary{{margin-bottom:24px}} .document-card{{background:var(--paper);border:1px solid var(--line);border-radius:14px;margin:0 0 28px;padding:25px;box-shadow:0 3px 14px #1820360b}}
.doc-header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}} h2{{margin:8px 0 2px;font-size:25px}} .filename{{color:var(--muted);margin:0}} .status{{font-size:12px;font-weight:700;padding:4px 9px;border-radius:99px}} .status.ok{{color:var(--green);background:#e5f5ed}} .status.warning,.status.review{{color:var(--amber);background:#fff0d3}}
.actions{{display:flex;gap:8px;flex-wrap:wrap}} .actions a{{border:1px solid var(--purple);color:var(--purple);padding:7px 10px;border-radius:7px;text-decoration:none;white-space:nowrap}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}} .stat{{display:grid;min-width:110px;background:#f6f2fb;border-radius:9px;padding:10px;color:var(--muted)}} .stat b{{font-size:20px;color:var(--purple)}}
details{{border-top:1px solid var(--line)}} summary{{cursor:pointer;font-weight:700;padding:14px 2px}} .section-body{{padding:0 2px 18px}} table{{width:100%;border-collapse:collapse}} th{{text-align:left;background:#f5f1f9;color:var(--purple)}} th,td{{border:1px solid var(--line);padding:9px;vertical-align:top}} .table-wrap{{overflow:auto}} ol{{margin-top:4px;padding-left:27px}} li{{margin:7px 0}} h4{{margin:14px 0 4px}} .prose{{white-space:pre-line;margin-top:0}} .empty{{color:var(--muted);font-style:italic}} .ok-text{{color:var(--green);font-weight:600}}
@media(max-width:850px){{.layout{{display:block}} aside{{position:static;height:auto}} nav{{display:none}} main{{padding:16px}} .doc-header{{display:block}} .actions{{margin-top:15px}}}}
</style></head><body><div class="layout"><aside><h1>PD Validation Report</h1><p>{complete} of {len(documents)} marked complete</p><nav>{nav}</nav></aside>
<main><div class="report-summary"><h1>Extraction validation</h1><p>Review extracted content against each linked Word source. Expand sections as needed.</p></div>{cards}</main></div></body></html>"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(page, encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an HTML validation report from extracted JSON")
    parser.add_argument("json_dir", type=Path)
    parser.add_argument("--samples", type=Path, default=Path("samples"))
    parser.add_argument("--output", type=Path, default=Path("output/validation-report.html"))
    args = parser.parse_args()
    print(generate_validation_report(args.json_dir, args.samples, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
