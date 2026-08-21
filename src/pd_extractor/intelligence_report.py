from __future__ import annotations

import argparse
import html
from pathlib import Path

from .database import connect_database, initialise_database
from .embeddings import DEFAULT_MODEL_NAME, load_sentence_transformer
from .mapping_suggestions import MappingSuggestion, suggest_mappings_for_pd, suggest_mappings_for_query
from .similarity import SimilarRole, _find_pd_id, find_similar_roles, search_roles


DEFAULT_PD_EXAMPLES = [
    "10613-01",
    "11283-01",
    "11349-01",
    "10773-02",
]

DEFAULT_QUERY_EXAMPLES = [
    "I am looking for a role which does policy analysis",
    "A role that manages procurement strategy and supplier governance",
    "A role that works on customer experience design and human centred design",
    "A role responsible for financial reporting and accounting",
]


def _h(value: object) -> str:
    return html.escape(str(value or ""))


def _score(value: float) -> str:
    return f"{value:.3f}"


def _pd_summary(connection, pd_id: int) -> dict[str, str]:
    row = connection.execute(
        """SELECT position_description_no, role_title, source_filename,
                  classification_grade_band
           FROM position_descriptions
           WHERE id = ?""",
        (pd_id,),
    ).fetchone()
    if row is None:
        raise KeyError(pd_id)
    mapping = connection.execute(
        """SELECT mapping_code, mapping_name, mapping_level, mapping_validated
           FROM active_pd_job_family_mappings
           WHERE position_description_id = ? AND mapping_rank = 1
           LIMIT 1""",
        (pd_id,),
    ).fetchone()
    return {
        "position_description_no": row["position_description_no"] or "",
        "role_title": row["role_title"] or "",
        "source_filename": row["source_filename"] or "",
        "classification_grade_band": row["classification_grade_band"] or "",
        "mapping": (
            f"{mapping['mapping_code']} — {mapping['mapping_name']} ({mapping['mapping_level']})"
            if mapping else ""
        ),
        "mapping_validated": mapping["mapping_validated"] if mapping else "",
    }


def _similar_roles_table(rows: list[SimilarRole]) -> str:
    body = []
    for row in rows:
        mapping = (
            f"{_h(row.primary_mapping_code)}<br>{_h(row.primary_mapping_name)}"
            if row.primary_mapping_code else "<span class=muted>Unmapped</span>"
        )
        body.append(
            "<tr>"
            f"<td>{_score(row.similarity)}</td>"
            f"<td>{_h(row.position_description_no)}</td>"
            f"<td>{_h(row.role_title)}</td>"
            f"<td>{mapping}</td>"
            f"<td>{_h(row.mapping_validated)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Similarity</th><th>PD</th><th>Role</th>"
        "<th>Primary mapping</th><th>Validated</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _suggestions_table(suggestions: list[MappingSuggestion]) -> str:
    cards = []
    for suggestion in suggestions:
        hierarchy = " → ".join(
            f"{_h(item['level'])}: {_h(item['name'])} <span class=muted>({_h(item['code'])})</span>"
            for item in suggestion.hierarchy
        )
        evidence = "".join(
            "<li>"
            f"{_h(item.position_description_no)} — {_h(item.role_title)} "
            f"<span class=muted>({_score(item.similarity)}, validated: {_h(item.mapping_validated)})</span>"
            "</li>"
            for item in suggestion.evidence[:5]
        )
        cards.append(
            "<div class=suggestion>"
            f"<div class=confidence>{_h(suggestion.confidence)}</div>"
            f"<h4>{_h(suggestion.mapping_code)} — {_h(suggestion.mapping_name)}</h4>"
            f"<p><b>Hierarchy:</b> {hierarchy or '<span class=muted>Not found in active framework</span>'}</p>"
            f"<p>{_h(suggestion.mapping_level)} · weighted score {_score(suggestion.weighted_score)} · "
            f"{suggestion.evidence_count} evidence roles · {suggestion.validated_evidence_count} validated</p>"
            f"<ul>{evidence}</ul>"
            "</div>"
        )
    return "".join(cards) if cards else "<p class=muted>No mapping suggestions available.</p>"


def generate_intelligence_report(
    database: Path,
    output: Path,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    pd_examples: list[str] | None = None,
    query_examples: list[str] | None = None,
) -> Path:
    pd_examples = pd_examples or DEFAULT_PD_EXAMPLES
    query_examples = query_examples or DEFAULT_QUERY_EXAMPLES
    connection = connect_database(database)
    try:
        initialise_database(connection)
        embedder = load_sentence_transformer(model_name)
        pd_sections = []
        for pd_identifier in pd_examples:
            try:
                pd_id = _find_pd_id(connection, pd_identifier)
            except KeyError:
                continue
            summary = _pd_summary(connection, pd_id)
            similar = find_similar_roles(connection, pd_id, model_name=model_name, limit=10)
            suggestions = suggest_mappings_for_pd(
                connection,
                pd_id,
                model_name=model_name,
                neighbour_limit=25,
                suggestion_limit=5,
            )
            pd_sections.append(
                "<section>"
                f"<h2>{_h(summary['position_description_no'])} — {_h(summary['role_title'])}</h2>"
                f"<p class=muted>{_h(summary['classification_grade_band'])} · {_h(summary['source_filename'])}</p>"
                f"<p><b>Current mapping:</b> {_h(summary['mapping']) or '<span class=muted>None</span>'} "
                f"<span class=muted>{_h(summary['mapping_validated'])}</span></p>"
                "<h3>Similar roles</h3>"
                f"{_similar_roles_table(similar)}"
                "<h3>Mapping suggestions</h3>"
                f"{_suggestions_table(suggestions)}"
                "</section>"
            )

        query_sections = []
        for query in query_examples:
            similar = search_roles(connection, query, embedder, model_name=model_name, limit=10)
            suggestions = suggest_mappings_for_query(
                connection,
                query,
                embedder,
                model_name=model_name,
                neighbour_limit=25,
                suggestion_limit=5,
            )
            query_sections.append(
                "<section>"
                f"<h2>Search: {_h(query)}</h2>"
                "<h3>Matching roles</h3>"
                f"{_similar_roles_table(similar)}"
                "<h3>Mapping suggestions</h3>"
                f"{_suggestions_table(suggestions)}"
                "</section>"
            )
    finally:
        connection.close()

    page = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>PD Intelligence Review</title>
<style>
body{{font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#f5f6fa;color:#172033}}
main{{max-width:1250px;margin:auto;padding:32px}}
h1,h2,h3{{color:#351052}} h1{{font-size:34px}} h2{{margin-top:0}}
section{{background:white;border:1px solid #dfe3ec;border-radius:14px;padding:22px;margin:22px 0;box-shadow:0 1px 2px #00000008}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0 20px}}
th,td{{border:1px solid #dde1e9;padding:8px;text-align:left;vertical-align:top}}
th{{background:#f2ecf7;color:#481579}}
.muted{{color:#667085}} .suggestion{{border:1px solid #ddd6e7;border-radius:12px;padding:14px;margin:12px 0;background:#fcfbff}}
.suggestion h4{{margin:0 0 4px;color:#172033}} .suggestion p{{margin:0 0 8px}}
.confidence{{float:right;background:#e8f7ef;color:#067647;border-radius:999px;padding:4px 10px;font-weight:700}}
ul{{margin:6px 0 0 20px}}
</style></head><body><main>
<h1>PD Intelligence Review</h1>
<p class=muted>Model: {_h(model_name)}. This report is for inspecting semantic search and job-family mapping suggestions.</p>
<h1>Existing PD examples</h1>
{''.join(pd_sections)}
<h1>Free-text search examples</h1>
{''.join(query_sections)}
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an HTML review report for PD intelligence features")
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--output", type=Path, default=Path("output/pd-intelligence-review.html"))
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--pd", action="append", dest="pds")
    parser.add_argument("--query", action="append", dest="queries")
    args = parser.parse_args()
    report = generate_intelligence_report(
        args.database,
        args.output,
        model_name=args.model,
        pd_examples=args.pds,
        query_examples=args.queries,
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
