from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import re
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .classifications import (
    classification_rows,
    seed_classification_references,
    update_classification_references,
)
from .config import default_database_path
from .database import (
    assign_job_family_mappings,
    connect_database,
    import_document,
    initialise_database,
    job_family_mappings_for_pd,
)
from .embeddings import DEFAULT_MODEL_NAME, framework_embedding_sources, load_sentence_transformer, upsert_embeddings
from .extractor import extract_document
from .intelligence_prepare import prepare_pd_intelligence
from .job_family_import import import_job_family_workbook
from .career_explorer_ui import render_career_explorer
from .career_explorer_reference_data import build_reference_payloads
from .mapping_suggestions import (
    _mapping_hierarchy,
    _to_jsonable,
    framework_similarity_scores_for_pd,
    framework_similarity_scores_for_query,
    suggest_mappings_for_pd,
    suggest_mappings_for_query,
)
from .mapping_assistant_ui import build_mapping_assistant_payload, render_mapping_assistant
from .similarity import _find_pd_id, find_similar_roles, search_roles


APP_VERSION = "2026-07-23-claude-ui-port-1"


_EMBEDDER_CACHE: dict[str, object] = {}


def _classification_backup_path(database_path: Path) -> Path:
    backup_dir = database_path.parent / "classification-reference-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return backup_dir / f"classifications-{stamp}.json"


def _classifications_csv(rows: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    fieldnames = [
        "raw_label",
        "usage_count",
        "display_label",
        "abbreviation",
        "cohort",
        "seniority_order",
        "enterprise_agreement",
        "active",
        "notes",
        "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _safe_docx_filename(filename: str) -> str:
    name = Path(filename or "").name
    name = re.sub(r"[^\w .()&,+-]+", "_", name, flags=re.UNICODE).strip(" .")
    if not name.lower().endswith(".docx"):
        raise ValueError("Only .docx Word files are supported for this prototype")
    return name or f"uploaded-pd-{datetime.now().strftime('%Y%m%d-%H%M%S')}.docx"


def _safe_workbook_filename(filename: str) -> str:
    name = Path(filename or "").name
    name = re.sub(r"[^\w .()&,+-]+", "_", name, flags=re.UNICODE).strip(" .")
    if not name.lower().endswith(".xlsx"):
        raise ValueError("Only .xlsx Excel workbooks are supported for job family imports")
    return name or f"job-family-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"


def _uploaded_pd_path(database_path: Path, filename: str) -> Path:
    upload_dir = database_path.parent / "uploaded-pds"
    upload_dir.mkdir(parents=True, exist_ok=True)
    candidate = upload_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return upload_dir / f"{stem}-{stamp}{suffix}"


def _uploaded_job_family_path(database_path: Path, filename: str) -> Path:
    upload_dir = database_path.parent / "job-family-imports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    candidate = upload_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return upload_dir / f"{stem}-{stamp}{suffix}"


def job_family_import_status(connection: sqlite3.Connection) -> dict:
    batch = connection.execute(
        """SELECT id, source_filename, source_path, framework_sheet, mapping_sheet,
                  imported_at, framework_rows, mapping_rows, is_active
           FROM job_family_import_batches
           WHERE is_active = 1
           ORDER BY id DESC
           LIMIT 1"""
    ).fetchone()
    if batch is None:
        return {
            "has_active_import": False,
            "framework_rows": 0,
            "mapping_rows": 0,
            "mapping_rows_linked_to_pds": 0,
            "invalid_mapping_codes": 0,
            "unlinked_mapping_rows": 0,
            "distinct_workbook_pd_ids": 0,
            "distinct_linked_db_pds": 0,
            "distinct_validated_workbook_pd_ids": 0,
            "distinct_validated_linked_db_pds": 0,
        }
    batch_id = int(batch["id"])
    counts = connection.execute(
        """SELECT
               COUNT(*) AS mapping_rows,
               SUM(CASE WHEN position_description_id IS NOT NULL THEN 1 ELSE 0 END)
                   AS mapping_rows_linked_to_pds,
               SUM(CASE WHEN framework_code_valid = 0 THEN 1 ELSE 0 END)
                   AS invalid_mapping_codes,
               SUM(CASE WHEN position_description_id IS NULL THEN 1 ELSE 0 END)
                   AS unlinked_mapping_rows,
               COUNT(DISTINCT CASE WHEN COALESCE(pd_id, '') <> '' THEN pd_id END)
                   AS distinct_workbook_pd_ids,
               COUNT(DISTINCT position_description_id)
                   AS distinct_linked_db_pds,
               COUNT(DISTINCT CASE
                   WHEN LOWER(TRIM(COALESCE(mapping_validated, ''))) IN ('yes', 'validated', 'true', 'y')
                        AND COALESCE(pd_id, '') <> ''
                   THEN pd_id END)
                   AS distinct_validated_workbook_pd_ids,
               COUNT(DISTINCT CASE
                   WHEN LOWER(TRIM(COALESCE(mapping_validated, ''))) IN ('yes', 'validated', 'true', 'y')
                   THEN position_description_id END)
                   AS distinct_validated_linked_db_pds
           FROM pd_job_family_mappings
           WHERE import_batch_id = ?""",
        (batch_id,),
    ).fetchone()
    output = dict(batch)
    output["has_active_import"] = True
    output["mapping_rows"] = int(counts["mapping_rows"] or 0)
    output["mapping_rows_linked_to_pds"] = int(counts["mapping_rows_linked_to_pds"] or 0)
    output["invalid_mapping_codes"] = int(counts["invalid_mapping_codes"] or 0)
    output["unlinked_mapping_rows"] = int(counts["unlinked_mapping_rows"] or 0)
    output["distinct_workbook_pd_ids"] = int(counts["distinct_workbook_pd_ids"] or 0)
    output["distinct_linked_db_pds"] = int(counts["distinct_linked_db_pds"] or 0)
    output["distinct_validated_workbook_pd_ids"] = int(counts["distinct_validated_workbook_pd_ids"] or 0)
    output["distinct_validated_linked_db_pds"] = int(counts["distinct_validated_linked_db_pds"] or 0)
    return output


def validation_queue(connection: sqlite3.Connection) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(
            """SELECT pd.id, pd.position_description_no, pd.role_title, pd.source_filename,
                      pd.extraction_status, pd.classification_grade_band,
                      vr.validation_status, vr.updated_at, vr.validated_at,
                      CASE
                          WHEN EXISTS (
                              SELECT 1 FROM embeddings e
                              WHERE e.source_type = 'pd' AND e.source_id = CAST(pd.id AS TEXT)
                          ) THEN 'Ready'
                          WHEN EXISTS (
                              SELECT 1 FROM pd_mapping_texts mt
                              WHERE mt.position_description_id = pd.id
                          ) THEN 'Mapping text only'
                          ELSE 'Not prepared'
                      END AS intelligence_status,
                      COUNT(ei.id) AS issue_count
               FROM position_descriptions pd
               JOIN validation_records vr ON vr.position_description_id = pd.id
               LEFT JOIN extraction_issues ei ON ei.position_description_id = pd.id
               WHERE vr.validation_status <> 'Validated'
               GROUP BY pd.id
               ORDER BY vr.updated_at DESC, pd.imported_at DESC"""
        )
    ]


def _embedder(model_name: str):
    if model_name not in _EMBEDDER_CACHE:
        _EMBEDDER_CACHE[model_name] = load_sentence_transformer(model_name)
    return _EMBEDDER_CACHE[model_name]


def search_pds(connection: sqlite3.Connection, query: str = "", limit: int = 50) -> list[dict]:
    if query.strip():
        like = f"%{query.strip()}%"
        rows = connection.execute(
            """SELECT pd.id, pd.position_description_no, pd.role_title,
                      pd.classification_grade_band, pd.source_filename,
                      cr.display_label AS classification_display,
                      cr.abbreviation AS classification_abbreviation,
                      cr.cohort AS classification_cohort,
                      cr.seniority_order AS classification_order,
                      m.mapping_code, m.mapping_name, m.mapping_level, m.mapping_validated
               FROM position_descriptions pd
               LEFT JOIN classification_references cr
                    ON cr.raw_label = pd.classification_grade_band
               LEFT JOIN active_pd_job_family_mappings m
                    ON m.position_description_id = pd.id AND m.mapping_rank = 1
               WHERE pd.position_description_no LIKE ?
                  OR pd.role_title LIKE ?
                  OR pd.source_filename LIKE ?
               ORDER BY pd.position_description_no
               LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT pd.id, pd.position_description_no, pd.role_title,
                      pd.classification_grade_band, pd.source_filename,
                      cr.display_label AS classification_display,
                      cr.abbreviation AS classification_abbreviation,
                      cr.cohort AS classification_cohort,
                      cr.seniority_order AS classification_order,
                      m.mapping_code, m.mapping_name, m.mapping_level, m.mapping_validated
               FROM position_descriptions pd
               LEFT JOIN classification_references cr
                    ON cr.raw_label = pd.classification_grade_band
               LEFT JOIN active_pd_job_family_mappings m
                    ON m.position_description_id = pd.id AND m.mapping_rank = 1
               ORDER BY pd.position_description_no
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def pd_detail(connection: sqlite3.Connection, pd_id: int) -> dict | None:
    row = connection.execute(
        """SELECT pd.id, pd.position_description_no, pd.role_title,
                  pd.classification_grade_band, pd.source_filename,
                  pd.extraction_status, mt.full_text,
                  cr.display_label AS classification_display,
                  cr.abbreviation AS classification_abbreviation,
                  cr.cohort AS classification_cohort,
                  cr.seniority_order AS classification_order,
                  m.mapping_code, m.mapping_name, m.mapping_level, m.mapping_validated
           FROM position_descriptions pd
           LEFT JOIN classification_references cr
                ON cr.raw_label = pd.classification_grade_band
           LEFT JOIN pd_mapping_texts mt ON mt.position_description_id = pd.id
           LEFT JOIN active_pd_job_family_mappings m
                ON m.position_description_id = pd.id AND m.mapping_rank = 1
           WHERE pd.id = ?""",
        (pd_id,),
    ).fetchone()
    return dict(row) if row else None


def resolve_pd_identifier(connection: sqlite3.Connection, value: str) -> int | None:
    token = str(value or "").strip()
    if not token:
        return None
    if re.fullmatch(r"\d{5}(?:-\d{2})?", token):
        row = connection.execute(
            """SELECT id
               FROM position_descriptions
               WHERE position_description_no = ?
                  OR position_description_no LIKE ?
               ORDER BY position_description_no DESC, id DESC
               LIMIT 1""",
            (token, f"{token}-%"),
        ).fetchone()
        if row:
            return int(row["id"])
    if token.isdigit():
        row = connection.execute(
            "SELECT id FROM position_descriptions WHERE id = ?",
            (int(token),),
        ).fetchone()
        if row:
            return int(row["id"])
    return None


def _similar_json(connection: sqlite3.Connection, rows) -> list[dict]:
    classifications = {
        int(row["id"]): row
        for row in connection.execute(
            """SELECT pd.id, pd.classification_grade_band,
                      cr.display_label, cr.abbreviation, cr.cohort, cr.seniority_order
               FROM position_descriptions pd
               LEFT JOIN classification_references cr
                    ON cr.raw_label = pd.classification_grade_band"""
        )
    }
    output = []
    for row in rows:
        hierarchy = _mapping_hierarchy(connection, row.primary_mapping_code)
        job_family = next((item for item in hierarchy if item.get("level") == "Job Family"), None)
        classification = classifications.get(row.position_description_id)
        output.append({
            "position_description_id": row.position_description_id,
            "position_description_no": row.position_description_no,
            "role_title": row.role_title,
            "source_filename": row.source_filename,
            "similarity": row.similarity,
            "primary_mapping_code": row.primary_mapping_code,
            "primary_mapping_name": row.primary_mapping_name,
            "primary_mapping_level": row.primary_mapping_level,
            "mapping_validated": row.mapping_validated,
            "mapping_hierarchy": hierarchy,
            "job_family_code": job_family["code"] if job_family else "",
            "job_family_name": job_family["name"] if job_family else "",
            "classification_raw": classification["classification_grade_band"] if classification else "",
            "classification_display": classification["display_label"] if classification else "",
            "classification_abbreviation": classification["abbreviation"] if classification else "",
            "classification_cohort": classification["cohort"] if classification else "",
            "classification_order": classification["seniority_order"] if classification else None,
        })
    return output


def career_explorer_payload(connection: sqlite3.Connection) -> dict:
    position_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(position_descriptions)")
    }
    role_id_expression = "pd.role_id" if "role_id" in position_columns else "'' AS role_id"
    rows = connection.execute(
        f"""WITH primary_mapping AS (
               SELECT m.*,
                      ROW_NUMBER() OVER (
                          PARTITION BY m.position_description_id
                          ORDER BY
                              CASE WHEN LOWER(COALESCE(m.mapping_validated, '')) = 'yes'
                                   THEN 0 ELSE 1 END,
                              COALESCE(m.framework_code_valid, 0) DESC,
                              m.id
                      ) AS selection_order
               FROM active_pd_job_family_mappings m
               WHERE m.mapping_rank = 1
           )
           SELECT pd.id, {role_id_expression}, pd.position_description_no, pd.role_title,
                  pd.classification_grade_band, pd.source_filename,
                  cr.display_label AS classification_display,
                  cr.abbreviation AS classification_abbreviation,
                  cr.cohort AS classification_cohort,
                  cr.seniority_order AS classification_order,
                  m.mapping_code, m.mapping_name, m.mapping_level, m.mapping_validated
           FROM position_descriptions pd
           LEFT JOIN classification_references cr
                ON cr.raw_label = pd.classification_grade_band
           LEFT JOIN primary_mapping m
                ON m.position_description_id = pd.id AND m.selection_order = 1
           ORDER BY COALESCE(cr.seniority_order, 9999), pd.role_title"""
    ).fetchall()
    purpose_rows = connection.execute(
        """SELECT position_description_id, section_text
           FROM pd_sections
           WHERE LOWER(section_name) IN ('primary_purpose', 'role purpose', 'purpose')"""
    ).fetchall()
    purposes = {int(row["position_description_id"]): row["section_text"] for row in purpose_rows}
    capability_rows = connection.execute(
        """SELECT pc.position_description_id, cd.capability_name
           FROM pd_capabilities pc
           JOIN capability_definitions cd ON cd.id = pc.capability_definition_id
           WHERE LOWER(COALESCE(pc.capability_type, '')) LIKE '%focus%'
           ORDER BY pc.position_description_id, pc.sequence"""
    ).fetchall()
    capabilities: dict[int, list[str]] = {}
    for row in capability_rows:
        capabilities.setdefault(int(row["position_description_id"]), [])
        name = str(row["capability_name"] or "")
        if name and name not in capabilities[int(row["position_description_id"])]:
            capabilities[int(row["position_description_id"])].append(name)

    roles = []
    family_codes: set[str] = set()
    grade_labels: set[str] = set()
    for row in rows:
        mapping_code = str(row["mapping_code"] or "")
        hierarchy = _mapping_hierarchy(connection, mapping_code) if mapping_code else []
        job_family = next(
            (item for item in hierarchy if "job family" in str(item.get("level", "")).lower()),
            None,
        )
        sub_family = next(
            (item for item in hierarchy if "sub" in str(item.get("level", "")).lower()),
            None,
        )
        grade = (
            row["classification_display"]
            or row["classification_abbreviation"]
            or row["classification_grade_band"]
            or ""
        )
        if grade:
            grade_labels.add(str(grade))
        if job_family and job_family.get("code"):
            family_codes.add(str(job_family["code"]))
        role_title = str(row["role_title"] or "")
        roles.append({
            "id": int(row["id"]),
            "role_id": row["role_id"] or "",
            "position_description_no": row["position_description_no"] or "",
            "role_title": role_title,
            "classification_raw": row["classification_grade_band"] or "",
            "classification_display": row["classification_display"] or "",
            "classification_abbreviation": row["classification_abbreviation"] or "",
            "classification_cohort": row["classification_cohort"] or "",
            "classification_order": row["classification_order"],
            "source_filename": row["source_filename"] or "",
            "mapping_code": mapping_code,
            "mapping_name": row["mapping_name"] or "",
            "mapping_level": row["mapping_level"] or "",
            "mapping_validated": row["mapping_validated"] or "",
            "job_family_code": job_family["code"] if job_family else "",
            "job_family_name": job_family["name"] if job_family else "Unmapped",
            "sub_family_code": sub_family["code"] if sub_family else "",
            "sub_family_name": sub_family["name"] if sub_family else "",
            "pathway": " > ".join(str(item.get("name") or "") for item in hierarchy if item.get("name")),
            "manager_role": bool(re.search(r"\b(manager|director|chief|lead)\b", role_title, re.I)),
            "purpose": purposes.get(int(row["id"]), ""),
            "capabilities": capabilities.get(int(row["id"]), []),
        })
    return {
        "roles": roles,
        "summary": {
            "role_count": len(roles),
            "job_family_count": len(family_codes),
            "grade_count": len(grade_labels),
        },
    }


def career_explorer_neighbours(
    connection: sqlite3.Connection,
    role_id: str,
    *,
    cursor: int = 0,
    anchored_role_ids: tuple[str, ...] = (),
) -> dict:
    """Return one replaceable three-role Constellation fan for a stable role ID.

    The published Constellation graph becomes authoritative automatically when it
    exists. Until then, the endpoint exposes the retained provisional graph and
    labels that fallback explicitly in the response.
    """
    role_id = str(role_id or "").strip()
    if not role_id or connection.execute(
        "SELECT 1 FROM position_descriptions WHERE role_id = ?", (role_id,)
    ).fetchone() is None:
        raise KeyError("Role not found")

    published = connection.execute(
        """SELECT algorithm_version
           FROM constellation_algorithm_versions
           WHERE status = 'published'
           ORDER BY created_at_utc DESC, algorithm_version DESC
           LIMIT 1"""
    ).fetchone()
    if published:
        algorithm_version = str(published["algorithm_version"])
        rows = connection.execute(
            """SELECT candidate_role_id AS role_id, rank_default AS neighbour_rank,
                      score, grade_delta,
                      act_plain_contribution + act_rare_contribution AS activity_contribution,
                      occupational_contribution,
                      adjacency_contribution,
                      grade_contribution AS classification_contribution,
                      source_release
               FROM constellation_candidate_scores
               WHERE algorithm_version = ? AND source_role_id = ?
                 AND rank_default IS NOT NULL
               ORDER BY rank_default, candidate_role_id""",
            (algorithm_version, role_id),
        ).fetchall()
        graph_source = "constellation_candidate_scores"
        provisional = False
    else:
        rows = connection.execute(
            """SELECT neighbour_role_id AS role_id,
                      CAST(neighbour_rank AS INTEGER) AS neighbour_rank,
                      CAST(score AS REAL) AS score,
                      CAST(grade_step_dg AS INTEGER) AS grade_delta,
                      CAST(activity_contribution AS REAL) AS activity_contribution,
                      CAST(subfamily_contribution AS REAL) AS occupational_contribution,
                      0.0 AS adjacency_contribution,
                      CAST(classification_contribution AS REAL) AS classification_contribution,
                      source_release, algorithm_version
               FROM role_neighbours
               WHERE role_id = ?
               ORDER BY CAST(neighbour_rank AS INTEGER), neighbour_role_id""",
            (role_id,),
        ).fetchall()
        graph_source = "role_neighbours"
        algorithm_version = str(rows[0]["algorithm_version"]) if rows else "provisional-1.0.0"
        provisional = True

    anchored = {str(value) for value in anchored_role_ids if value}
    available = [row for row in rows if str(row["role_id"]) not in anchored]
    total = len(available)
    start = max(0, int(cursor))
    if total and start >= total:
        start = 0
    page = available[start : start + 3]
    end = start + len(page)
    next_cursor = 0 if end >= total else end

    items = []
    for row in page:
        items.append({
            "role_id": str(row["role_id"]),
            "rank": int(row["neighbour_rank"]),
            "score": float(row["score"] or 0),
            "grade_delta": int(row["grade_delta"] or 0),
            "components": {
                "activity": float(row["activity_contribution"] or 0),
                "occupation": float(row["occupational_contribution"] or 0),
                "adjacency": float(row["adjacency_contribution"] or 0),
                "grade": float(row["classification_contribution"] or 0),
            },
        })

    return {
        "source_role_id": role_id,
        "items": items,
        "cursor": start,
        "next_cursor": next_cursor,
        "total": total,
        "counter": f"{start + 1}\u2013{end} of {total}" if page else "0 of 0",
        "algorithm": {
            "version": algorithm_version,
            "source_release": str(rows[0]["source_release"]) if rows else "",
            "graph_source": graph_source,
            "provisional": provisional,
        },
    }


HTML = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>PD Role Intelligence</title>
<style>
:root{--purple:#481579;--ink:#172033;--muted:#667085;--line:#d7dce6;--bg:#f4f6fa;--green:#067647;--amber:#9a5a00}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,Segoe UI,sans-serif}
.layout{display:grid;grid-template-columns:360px minmax(0,1fr);min-height:100vh}.side{background:#211238;color:white;padding:22px;height:100vh;position:sticky;top:0;overflow:auto}
.side h1{margin:0;font-size:22px}.side p{margin:4px 0 18px;color:#d5cbe1}input,textarea{width:100%;border:1px solid #c8cfda;border-radius:9px;padding:10px;font:inherit}textarea{min-height:95px}
button{border:1px solid var(--purple);background:white;color:var(--purple);padding:9px 12px;border-radius:9px;cursor:pointer;font-weight:650}button.primary{background:var(--purple);color:white}.toplink{display:block;color:white;text-decoration:none;border:1px solid #ffffff55;border-radius:9px;padding:9px 10px;margin:0 0 16px}.toplink:hover{background:#ffffff1b}
.search-row{display:flex;gap:8px;margin:10px 0 16px}.pd-list{display:grid;gap:6px}.pd-btn{width:100%;text-align:left;border:0;background:transparent;color:white;padding:9px;border-radius:8px}.pd-btn:hover,.pd-btn.active{background:#ffffff1b}.pd-btn small{display:block;color:#d5cbe1}
main{padding:26px;max-width:1280px}.card{background:white;border:1px solid var(--line);border-radius:14px;padding:20px;margin:0 0 18px;box-shadow:0 1px 2px #00000008}
h2,h3{color:#351052}h2{margin:0 0 4px}.muted{color:var(--muted)}.pill{display:inline-block;border-radius:999px;padding:3px 9px;background:#e8f7ef;color:var(--green);font-weight:700;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dde1e9;padding:8px;text-align:left;vertical-align:top}th{background:#f2ecf7;color:#481579}.suggestion{border:1px solid #ddd6e7;background:#fcfbff;border-radius:12px;padding:14px;margin:10px 0}.confidence{float:right;background:#e8f7ef;color:#067647;border-radius:999px;padding:4px 10px;font-weight:700}.hier{margin:6px 0}.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}.loading{opacity:.65}.filters{border:1px solid var(--line);border-radius:10px;background:#fafbfe;padding:10px;margin:10px 0 14px}.filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.filters label{display:block;margin:6px 0}.filters input{width:auto;margin-right:6px}.filters button{float:right;padding:4px 8px;font-size:12px}.grade{font-weight:700;color:#351052}.small{font-size:12px;color:var(--muted)}@media(max-width:900px){.layout{display:block}.side{height:auto;position:static}.two{grid-template-columns:1fr}.filter-grid{grid-template-columns:1fr}}
</style></head><body><div class=layout><aside class=side>
<h1>PD Role Intelligence</h1><p>Similar roles, semantic search, and mapping suggestions.</p>
<a class=toplink href="/admin/classifications">Classification admin</a>
<label>Find an existing PD</label><div class=search-row><input id=pdSearch placeholder="PD number or role title"><button onclick="searchPDs()">Search</button></div>
<div id=pdList class=pd-list></div>
</aside><main>
<section class=card><h2>Free-text role search</h2><p class=muted>Describe a role you are thinking of. The app searches by meaning, not just exact words.</p>
<textarea id=query placeholder="e.g. I am looking for a role which does policy analysis"></textarea>
<div class=search-row><button class=primary onclick="runQuery()">Search roles and suggest mappings</button></div></section>
<div id=content><section class=card><h2>Select or search</h2><p>Choose a PD from the left, or run a free-text search above.</p></section></div>
</main></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});const j=await r.json();if(!r.ok)throw new Error(j.error||'Request failed');return j}
function grade(row){const abbr=row.classification_abbreviation||'';const label=row.classification_display||row.classification_raw||row.classification_grade_band||'';const cohort=row.classification_cohort||'';if(!abbr&&!label)return '<span class=muted>Unclassified</span>';return `<span class=grade>${esc(abbr||label)}</span>${abbr&&label?`<br><span class=small>${esc(label)}</span>`:''}${cohort?`<br><span class=small>${esc(cohort)}</span>`:''}`}
function mapping(row){const code=row.primary_mapping_code||row.mapping_code,name=row.primary_mapping_name||row.mapping_name,level=row.primary_mapping_level||row.mapping_level;if(!code)return '<span class=muted>Unmapped</span>';const h=(row.mapping_hierarchy||[]).map(x=>`${esc(x.level)}: ${esc(x.name)}`).join('<br>');return `${esc(code)}<br>${esc(name)}<br><span class=muted>${esc(level)}</span>${h?`<div class=muted style="margin-top:5px">${h}</div>`:''}`}
let familyRankHints={};
function suggestionFamilyRanks(suggestions){const ranks={};(suggestions||[]).forEach((s,i)=>{const jf=(s.hierarchy||[]).find(h=>h.level==='Job Family');if(jf&&jf.code&&ranks[jf.code]===undefined)ranks[jf.code]=i+1});return ranks}
function jobFamilyOptions(rows,id){const seen=new Map();rows.forEach(r=>{if(r.job_family_code)seen.set(r.job_family_code,r.job_family_name)});const ranks=familyRankHints[id]||{};return [...seen.entries()].sort((a,b)=>(ranks[a[0]]??9999)-(ranks[b[0]]??9999)||a[1].localeCompare(b[1]))}
function cohortOptions(rows){const seen=new Map();rows.forEach(r=>{if(r.classification_cohort)seen.set(r.classification_cohort,Number(r.classification_order??9999))});return [...seen.entries()].sort((a,b)=>a[1]-b[1]||a[0].localeCompare(b[0])).map(([name])=>name)}
function filterPanel(id,rows){const families=jobFamilyOptions(rows,id);const cohorts=cohortOptions(rows);const ranks=familyRankHints[id]||{};if(!families.length&&!cohorts.length)return '<p class=muted>No mapped job-family or classification filters available for this result set.</p>';return `<div class=filters id="${id}"><button onclick="clearFilters('${id}')">Clear</button><div class=filter-grid><div><b>Filter by job family</b>${families.length?families.map(([code,name])=>`<label><input data-kind=family type=checkbox value="${esc(code)}" onchange="applyFilters('${id}')"> ${ranks[code]?`<span class=small>#${ranks[code]} suggestion</span> `:''}${esc(name)} <span class=muted>(${esc(code)})</span></label>`).join(''):'<p class=muted>No mapped families in this result set.</p>'}</div><div><b>Filter by classification cohort</b>${cohorts.length?cohorts.map(name=>`<label><input data-kind=cohort type=checkbox value="${esc(name)}" onchange="applyFilters('${id}')"> ${esc(name)}</label>`).join(''):'<p class=muted>No cohorts in this result set.</p>'}</div></div></div>`}
function filteredRows(id,rows){const families=[...document.querySelectorAll(`#${id} input[data-kind=family]:checked`)].map(x=>x.value);const cohorts=[...document.querySelectorAll(`#${id} input[data-kind=cohort]:checked`)].map(x=>x.value);return rows.filter(r=>(!families.length||families.includes(r.job_family_code))&&(!cohorts.length||cohorts.includes(r.classification_cohort)))}
function similarTable(rows){return `<table><thead><tr><th>Similarity</th><th>PD</th><th>Role</th><th>Grade</th><th>Primary mapping</th><th>Validated</th></tr></thead><tbody>${rows.slice(0,10).map(r=>`<tr><td>${Number(r.similarity).toFixed(3)}</td><td>${esc(r.position_description_no)}</td><td>${esc(r.role_title)}</td><td>${grade(r)}</td><td>${mapping(r)}</td><td>${esc(r.mapping_validated)}</td></tr>`).join('')}</tbody></table>`}
let resultSets={};
var frameworkScoreSets=window.frameworkScoreSets||{};
window.frameworkScoreSets=frameworkScoreSets;
function resultBlock(id,heading,rows,suggestions=[]){resultSets[id]=rows;familyRankHints[id]=suggestionFamilyRanks(suggestions);return `<h2>${esc(heading)}</h2>${filterPanel(id,rows)}<div id="${id}-table">${similarTable(rows)}</div><p class=muted>Showing top 10 of <span id="${id}-count">${rows.length}</span> matching roles after filters.</p>`}
function applyFilters(id){const rows=filteredRows(id,resultSets[id]||[]);document.querySelector(`#${id}-table`).innerHTML=similarTable(rows);document.querySelector(`#${id}-count`).textContent=rows.length}
function clearFilters(id){document.querySelectorAll(`#${id} input`).forEach(x=>x.checked=false);applyFilters(id)}
function suggestionsHtml(rows){if(!rows.length)return '<p class=muted>No mapping suggestions available.</p>';return rows.map(s=>{const hier=(s.hierarchy||[]).map(h=>`${esc(h.level)}: ${esc(h.name)} <span class=muted>(${esc(h.code)})</span>`).join(' → ');const ev=(s.evidence||[]).slice(0,6).map(e=>`<li>${esc(e.position_description_no)} — ${esc(e.role_title)} <span class=muted>(${Number(e.similarity).toFixed(3)}, validated: ${esc(e.mapping_validated)})</span></li>`).join('');return `<div class=suggestion><div class=confidence>${esc(s.confidence)}</div><h3>${esc(s.mapping_code)} — ${esc(s.mapping_name)}</h3><div class=hier><b>Hierarchy:</b> ${hier||'<span class=muted>Not found</span>'}</div><p class=muted>${esc(s.mapping_level)} · weighted score ${Number(s.weighted_score).toFixed(3)} · ${s.evidence_count} evidence roles · ${s.validated_evidence_count} validated</p><ul>${ev}</ul></div>`}).join('')}
async function searchPDs(){const q=document.querySelector('#pdSearch').value;const rows=await api('/api/pds?q='+encodeURIComponent(q));document.querySelector('#pdList').innerHTML=rows.map(r=>`<button class=pd-btn onclick="loadPD(${r.id})">${esc(r.position_description_no)} — ${esc(r.role_title)}<small>${esc(r.mapping_name||'Unmapped')}</small></button>`).join('')||'<p class=muted>No matches.</p>'}
async function loadPD(id){document.querySelector('#content').innerHTML='<section class=card><h2>Loading…</h2></section>';const data=await api('/api/pds/'+id+'/intelligence');const d=data.pd;document.querySelector('#content').innerHTML=`<section class=card><h2>${esc(d.position_description_no)} — ${esc(d.role_title)}</h2><p class=muted>${esc(d.classification_grade_band)} · ${esc(d.source_filename)}</p><p><b>Current mapping:</b> ${d.mapping_code?`${esc(d.mapping_code)} — ${esc(d.mapping_name)} (${esc(d.mapping_level)})`:'<span class=muted>Unmapped</span>'} ${d.mapping_validated?`<span class=pill>${esc(d.mapping_validated)}</span>`:''}</p></section><div class=two><section class=card>${resultBlock('pd-similar','Similar roles',data.similar_roles)}</section><section class=card><h2>Mapping suggestions</h2>${suggestionsHtml(data.mapping_suggestions)}</section></div>`}
async function runQuery(){const q=document.querySelector('#query').value.trim();if(!q)return;document.querySelector('#content').innerHTML='<section class=card><h2>Searching…</h2><p class=muted>The first search may take a moment while the model loads.</p></section>';const data=await api('/api/search?query='+encodeURIComponent(q));document.querySelector('#content').innerHTML=`<section class=card><h2>Search results</h2><p class=muted>${esc(q)}</p></section><div class=two><section class=card>${resultBlock('query-results','Matching roles',data.roles)}</section><section class=card><h2>Mapping suggestions</h2>${suggestionsHtml(data.mapping_suggestions)}</section></div>`}
async function runQuery(){const q=document.querySelector('#query').value.trim();if(!q)return;document.querySelector('#content').innerHTML='<section class=card><h2>Searching...</h2><p class=muted>The first search may take a moment while the model loads.</p></section>';try{const data=await api('/api/search?query='+encodeURIComponent(q));document.querySelector('#content').innerHTML=`<section class=card><h2>Search results</h2><p class=muted>${esc(q)}</p></section><div class=two><section class=card>${resultBlock('query-results','Matching roles',data.roles||[])}</section><section class=card><h2>Mapping suggestions</h2>${suggestionsHtml(data.mapping_suggestions||[])}</section></div>`}catch(err){document.querySelector('#content').innerHTML=`<section class=card><h2>Search failed</h2><p class=muted>${esc(err.message||err)}</p><p>Try refreshing the page. If it keeps happening, tell Codex the exact search phrase.</p></section>`}}
searchPDs();
</script></body></html>"""


HTML_V2 = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>PD Role Intelligence</title>
<style>
:root{--purple:#481579;--purple2:#082646;--ink:#172033;--muted:#667085;--line:#d7dce6;--bg:#f6f8fb;--green:#067647;--soft:#f7f2fb;--panel:#ffffff}
*{box-sizing:border-box}body{margin:0;color:var(--ink);font:15px/1.45 system-ui,Segoe UI,sans-serif;background:radial-gradient(#d7dce6 1px,transparent 1px) 0 0/18px 18px,var(--bg)}
.app{width:calc(100% - 56px);max-width:1600px;margin:28px auto;background:#fff;border:1px solid var(--line);border-radius:12px;min-height:calc(100vh - 56px);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 8px 24px #10203312}.side{background:#fff;color:var(--ink);padding:0 56px;height:auto;position:static;border-bottom:1px solid #e5e9f0;display:flex;align-items:center;justify-content:space-between;min-height:56px}
.brand{font-size:17px;font-weight:800;margin:0;color:var(--purple2);text-decoration:none;white-space:nowrap}.tag{display:none}.nav{display:flex;gap:22px;align-items:center}.nav button,.nav a{border:0;border-bottom:3px solid transparent;background:transparent;color:var(--muted);padding:18px 0 14px;border-radius:0;text-decoration:none;font:inherit;font-weight:700;cursor:pointer;white-space:nowrap}.nav button:hover,.nav button.active,.nav a:hover{background:transparent;color:var(--purple2);border-bottom-color:var(--purple2)}
main{padding:0;max-width:none;flex:1;display:flex;flex-direction:column}.view{display:none;padding:34px 56px 42px}.view.active{display:block}.hero{background:transparent;border:0;border-radius:0;padding:28px 0 32px;margin:0 auto 18px;max-width:650px;text-align:center}.hero h1{margin:0 0 12px;color:var(--purple2);font-size:30px;letter-spacing:-.02em}.hero p{font-size:17px}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,340px));gap:22px;justify-content:center;margin:18px auto 34px}.card{background:white;border:1px solid var(--line);border-radius:6px;padding:22px;margin:0 0 18px;box-shadow:0 1px 2px #00000005}.card h2,.card h3{color:var(--purple2);margin-top:0}.cardbutton{position:relative;display:block;text-align:left;width:100%;min-height:190px;border:1px solid var(--line);border-radius:5px;background:white;padding:34px 36px;cursor:pointer;color:var(--ink);transition:.15s ease}.cardbutton:hover{border-color:#b7c0cf;box-shadow:0 8px 22px #10203312;transform:translateY(-1px)}.cardbutton h3{font-size:22px;margin:22px 0 8px;color:var(--purple2)}.cardbutton p{max-width:270px;font-size:15px}.workflow-icon{font-size:24px;color:var(--purple2);font-weight:800}.workflow-arrow{position:absolute;right:36px;top:34px;color:#778195;font-size:28px}.home-version{text-align:center;margin:0 0 42px}.home-version span{display:inline-block;background:#eef2f7;color:#667085;border-radius:3px;padding:5px 10px;font-size:12px;font-weight:700}.app-footer{margin-top:auto;border-top:1px solid #e5e9f0;padding:28px 56px;display:flex;justify-content:space-between;color:var(--purple2);font-size:13px}.footer-links{display:flex;gap:28px;color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:12px;color:var(--muted)}.pill{display:inline-block;border-radius:999px;padding:3px 9px;background:#e8f7ef;color:var(--green);font-weight:700;font-size:12px}.grade{font-weight:800;color:var(--purple2)}
input,textarea{width:100%;border:1px solid #c8cfda;border-radius:10px;padding:11px;font:inherit}textarea{min-height:110px}button,.button{border:1px solid var(--purple);background:white;color:var(--purple);padding:10px 13px;border-radius:10px;cursor:pointer;font-weight:700;text-decoration:none;display:inline-block}button.primary,.button.primary{background:var(--purple);color:white}.toolbar{display:flex;gap:10px;align-items:center;margin:10px 0 16px}.split{display:grid;grid-template-columns:minmax(300px,420px) minmax(0,1fr);gap:18px}.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}.mapping-layout{display:grid;gap:18px}.mapping-picker{padding-bottom:14px}.mapping-picker .toolbar{max-width:720px}.mapping-picker .pd-list{grid-template-columns:repeat(auto-fit,minmax(260px,1fr));max-height:none}.mapping-summary{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:start}.mapping-summary h2{margin-bottom:6px}.mapping-summary p{margin:4px 0}
.pd-list{display:grid;gap:8px;max-height:70vh;overflow:auto}.pd-btn{width:100%;text-align:left;border:1px solid var(--line);background:white;color:var(--ink);padding:10px;border-radius:10px}.pd-btn:hover{border-color:var(--purple);background:#fcfbff}.pd-btn small{display:block;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dde1e9;padding:8px;text-align:left;vertical-align:top}th{background:#f2ecf7;color:var(--purple)}
.filters{border:1px solid var(--line);border-radius:12px;background:#fafbfe;padding:12px;margin:10px 0 14px}.filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.filters label{display:block;margin:6px 0}.filters input{width:auto;margin-right:6px}.filters button{float:right;padding:4px 8px;font-size:12px}
.suggestion{border:1px solid #ddd6e7;background:#fcfbff;border-radius:12px;padding:14px;margin:10px 0}.confidence{float:right;background:#e8f7ef;color:#067647;border-radius:999px;padding:4px 10px;font-weight:700}.admin-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.decision-guide{border:1px solid #ddd6e7;background:linear-gradient(135deg,#fff,#fbf8ff);border-radius:14px;padding:18px;margin:0 0 18px}.decision-guide h2{margin-bottom:6px}.decision-guide>.muted{margin-top:0}.guide-pager{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:12px 0}.guide-pager .small{font-weight:700}.family-strip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.family-card{width:100%;min-height:92px;text-align:left;border:1px solid #ddd6e7;background:white;border-radius:14px;padding:14px;color:var(--ink)}.family-card:hover,.family-card.active{border-color:var(--purple);box-shadow:0 2px 8px #00000012;background:#fcfbff}.family-rank{display:inline-flex;align-items:center;justify-content:center;background:var(--purple);color:white;width:26px;height:26px;border-radius:999px;font-weight:800;margin-right:8px}.family-name{font-size:16px;font-weight:900;color:var(--purple2);text-transform:uppercase;letter-spacing:.01em}.family-meta{display:block;margin-top:6px;color:var(--muted);font-size:12px;font-weight:700}.guide-explorer{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}.subfamily-stage{position:relative;min-height:392px;margin-top:8px}.subfamily-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;align-items:start}.subfamily-column{display:grid;gap:14px}.subfamily-card{width:100%;min-height:112px;text-align:left;border:2px solid #05364a;background:#176c86;color:white;border-radius:18px;padding:15px 18px;box-shadow:inset 0 -2px 0 #06384b;cursor:pointer}.subfamily-card:hover,.subfamily-card.active{background:#0f5d76;box-shadow:0 6px 18px #1020331c}.subfamily-card b{display:block;font-size:16px;line-height:1.2;letter-spacing:.01em}.subfamily-card .small{color:#e3f3f7;font-size:12px}.empty-subfamily{border:1px dashed var(--line);border-radius:16px;padding:18px;color:var(--muted);background:#fff}.spec-backdrop{position:absolute;inset:0;z-index:4;background:rgba(255,255,255,.18);border-radius:18px}.specialisation-panel{position:absolute;top:0;width:calc(50% - 9px);min-height:238px;z-index:5;border:2px solid #176c86;background:#f5fbfd;border-radius:18px;padding:16px;box-shadow:0 12px 30px #10203324}.specialisation-panel.left{left:calc(50% + 9px)}.specialisation-panel.right{left:0}.spec-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:1fr;gap:12px}.spec-card,.shortlist-card{border:1px solid var(--line);background:white;border-radius:14px;padding:14px;text-align:left}.spec-card{min-height:190px;display:flex;flex-direction:column}.spec-card .primary{margin-top:auto;align-self:flex-start}.spec-card h4,.shortlist-card h4{margin:0 0 8px;color:var(--purple2)}.guide-score{float:right;background:#f2ecf7;color:var(--purple);border-radius:999px;padding:2px 8px;font-size:12px;font-weight:800}.shortlist{border-top:1px solid var(--line);margin-top:14px;padding-top:14px}.shortlist-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.shortlist-empty{border:1px dashed var(--line);border-radius:12px;padding:14px;color:var(--muted);background:#fff}.review-detail{margin-top:14px;border:1px solid #ddd6e7;background:#fff;border-radius:14px;padding:16px}
.mapping-workflow{display:grid;grid-template-columns:260px minmax(0,1fr);gap:0;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:white}.mapping-rail{background:#eef4ff;border-right:1px solid var(--line);padding:28px 24px;display:flex;flex-direction:column;gap:24px}.mapping-rail h3{font-size:13px;text-transform:uppercase;letter-spacing:.12em;color:#5e6a7c;margin:0 0 12px}.mapping-step{display:grid;grid-template-columns:42px minmax(0,1fr);gap:14px;align-items:center}.step-dot{width:36px;height:36px;border-radius:999px;display:grid;place-items:center;font-weight:900;background:#dbe9ff;color:#4e6079;border:1px solid #c6d6ef}.mapping-step.done .step-dot,.mapping-step.active .step-dot{background:#05284a;color:white;border-color:#05284a}.step-title{font-weight:900;color:var(--ink)}.step-state{font-size:12px;color:var(--muted);font-weight:700}.mapping-guide-note{margin-top:auto;border-top:1px solid #cad5e6;padding-top:18px}.mapping-guide-note div{background:#e2edff;border-radius:10px;padding:14px;font-size:13px;color:#40506a}.mapping-main{padding:28px 38px 116px}.assist-summary{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;align-items:center;border:1px solid #cfd6e2;border-radius:8px;padding:18px 22px;margin-bottom:34px}.assist-title-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.pd-chip{background:#dbe9ff;color:#05284a;padding:4px 9px;border-radius:3px;font-weight:900;font-size:13px}.assist-summary h2{margin:0;font-size:24px}.assist-summary .meta{display:flex;gap:18px;color:var(--muted);font-weight:700;margin-top:6px}.validation-badge{background:#dbe9ff;color:#05284a;border:1px solid #adc6ed;border-radius:3px;padding:8px 13px;font-weight:900}.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:4px 0 12px}.section-head h2{margin:0;font-size:24px}.suggested-note{font-size:13px;color:var(--muted);font-weight:800}.family-choices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;border-top:1px solid var(--line);padding-top:20px}.family-option{display:grid;grid-template-columns:48px minmax(0,1fr) 28px;gap:16px;align-items:center;text-align:left;border:1px solid #d8dde6;background:white;border-radius:2px;padding:18px 18px;color:var(--ink);min-height:94px}.family-option:hover,.family-option.active{border-color:#05284a;box-shadow:inset 0 0 0 1px #05284a;background:#fbfdff}.family-icon{width:40px;height:40px;border-radius:4px;background:#eef3fb;display:grid;place-items:center;color:#05284a;font-weight:900}.radio-dot{width:20px;height:20px;border-radius:999px;border:3px solid #cbd2dc}.family-option.active .radio-dot{border-color:#05284a;box-shadow:inset 0 0 0 4px white;background:#05284a}.family-option .family-name{font-size:16px;text-transform:none;color:var(--ink);letter-spacing:0}.family-option .family-meta{font-size:12px;color:var(--muted);font-weight:700}.drill-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;border-top:1px solid var(--line);margin-top:34px;padding-top:26px}.drill-label{font-size:13px;text-transform:uppercase;letter-spacing:.14em;color:#6d6f76;font-weight:900;margin:0 0 14px}.subfamily-list{border:1px solid #d8dde6;border-left:4px solid #cbd2dc}.subfamily-row{width:100%;display:grid;grid-template-columns:minmax(0,1fr) 24px;gap:12px;align-items:center;border:0;border-bottom:1px solid #d8dde6;border-radius:0;background:white;color:#253348;text-align:left;padding:18px 22px}.subfamily-row:last-child{border-bottom:0}.subfamily-row.active,.subfamily-row:hover{background:#f2f5f9;color:#05284a}.subfamily-row.active{box-shadow:inset 4px 0 0 #05284a}.subfamily-row b{font-size:18px}.chevron{color:#05284a;font-size:26px;line-height:1}.specialisation-list{display:grid;gap:14px}.specialisation-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;border:1px solid #d8dde6;background:white;border-radius:2px;padding:16px 18px;min-height:86px}.specialisation-card h4{margin:0 0 4px;font-size:18px;color:var(--ink)}.specialisation-card p{margin:0;color:var(--muted);font-size:13px}.empty-panel{border:1px dashed var(--line);border-radius:8px;padding:20px;color:var(--muted);background:#fbfdff}.shortlist-bar{position:sticky;bottom:16px;z-index:20;margin:24px auto 0;max-width:1040px;background:#05284a;color:white;border-radius:8px;padding:14px 16px;display:grid;grid-template-columns:44px minmax(0,1fr) auto 34px;gap:14px;align-items:center;box-shadow:0 14px 34px #05284a35}.shortlist-icon{width:38px;height:38px;border-radius:10px;border:2px solid #6480a3;display:grid;place-items:center;font-weight:900}.shortlist-title{font-weight:900}.shortlist-items{font-size:13px;color:#cbd8e9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.shortlist-bar button{background:white;color:#05284a;border-color:white;border-radius:2px;padding:12px 26px}.shortlist-close{font-size:28px;color:#aac0dc;text-align:center}.review-detail{border-color:#cfd6e2;background:#fbfdff}.evidence-heading{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-top:30px}.evidence-heading h2{margin:0}.mapping-workflow table th{background:#e6eefc;color:#555;letter-spacing:.08em;text-transform:uppercase;font-size:12px}.mapping-workflow table td{font-size:13px}.shortlist-review{border:1px solid #b9c9df;background:#f7faff;border-radius:8px;padding:22px;margin:22px 0}.shortlist-review-head{display:flex;justify-content:space-between;gap:18px;align-items:start;margin-bottom:16px}.shortlist-review-head h3{margin:0 0 4px;color:#05284a;font-size:22px}.selection-count{background:#e2edff;color:#05284a;border-radius:999px;padding:6px 11px;font-weight:900;white-space:nowrap}.shortlist-review-list{display:grid;gap:10px}.shortlist-review-option{display:grid;grid-template-columns:24px minmax(0,1fr) auto;gap:14px;align-items:start;border:1px solid #d3dbe7;background:white;border-radius:6px;padding:15px;cursor:pointer}.shortlist-review-option:has(input:checked){border-color:#05284a;box-shadow:inset 4px 0 0 #05284a;background:#fbfdff}.shortlist-review-option input{width:18px;height:18px;margin:3px 0 0}.shortlist-review-option h4{margin:0 0 4px;color:#05284a;font-size:17px}.shortlist-review-option p{margin:3px 0;color:var(--muted);font-size:13px}.shortlist-review-actions{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:18px}.assignment-status{margin-right:auto;font-size:13px;color:var(--muted)}.assigned-summary{border:1px solid #a7d7bf;background:#f0fbf5;border-radius:7px;padding:12px 14px;margin-top:12px}.assigned-summary b{color:#067647}.assigned-list{margin:6px 0 0;padding-left:20px}.assigned-list li{margin:3px 0}.family-description{display:block;margin-top:6px;color:#526077;font-size:13px;font-weight:500;line-height:1.35}.remove-shortlist{border:0;background:transparent;color:#7d3b3b;padding:3px 7px}.assign-success{border:1px solid #8ecbaa;background:#edf9f2;color:#075c39;border-radius:6px;padding:12px 14px;margin-top:14px;font-weight:800}
@media(max-width:1000px){.app{margin:0;border-radius:0;min-height:100vh}.side{padding:0 22px;display:block}.nav{gap:14px;flex-wrap:wrap}.view{padding:24px 22px}.cards,.split,.two,.filter-grid,.admin-grid{grid-template-columns:1fr}.cardbutton{min-height:150px}.app-footer{padding:22px;display:block}.footer-links{margin-top:10px}}
</style></head><body><div class=app><aside class=side>
<a class=brand href="/">PD Manager</a><p class=tag>Search, compare and map position descriptions.</p>
<nav class=nav aria-label="Primary navigation">
<button data-view=upload onclick="showView('upload')">Upload</button>
<a href="http://127.0.0.1:8765/">Validation Queue</a>
<button data-view=library onclick="showView('library')">Search</button>
<button data-view=mapping onclick="showView('mapping')">Mapping Assistant</button>
<a href="/admin/classifications">Classification Admin</a>
<button data-view=workbook onclick="showView('workbook')">Mapping Workbook Import</button>
</nav>
</aside><main>
<section id=home class="view active">
<div class=hero><h1>PD Management System</h1><p class=muted>Select a workflow to manage, validate, search and map position descriptions.</p></div>
<div class=cards>
<button class=cardbutton onclick="showView('upload')"><span class=workflow-icon>⇧</span><span class=workflow-arrow>→</span><h3>Upload Position Description</h3><p class=muted>Ingest and process a new Word document for structured review.</p></button>
<button class=cardbutton onclick="window.location.href='http://127.0.0.1:8765/'"><span class=workflow-icon>☑</span><span class=workflow-arrow>→</span><h3>Validation Queue</h3><p class=muted>Review and validate extracted data from uploaded PDs.</p></button>
<button class=cardbutton onclick="showView('library')"><span class=workflow-icon>⌕</span><span class=workflow-arrow>→</span><h3>Search Roles</h3><p class=muted>Find existing position descriptions by ID, title, or role content.</p></button>
<button class=cardbutton onclick="showView('mapping')"><span class=workflow-icon>◇</span><span class=workflow-arrow>→</span><h3>Mapping Assistant</h3><p class=muted>Select and assign job family mappings using similar-role evidence.</p></button>
<button class=cardbutton onclick="window.location.href='/admin/classifications'"><span class=workflow-icon>⚙</span><span class=workflow-arrow>→</span><h3>Classification Admin</h3><p class=muted>Maintain grade labels, abbreviations, cohorts and display order.</p></button>
<button class=cardbutton onclick="showView('workbook')"><span class=workflow-icon>⇧</span><span class=workflow-arrow>→</span><h3>Mapping Workbook Import</h3><p class=muted>Replace the active job-family framework and mapping reference data.</p></button>
</div><div class=home-version><span>Prototype Version: Local MVP</span></div></section>

<section id=library class=view>
<div class=hero><h1>PD Library</h1><p class=muted>Use this when you know the role title, PD ID, or part of the source filename.</p></div>
<div class=split><section class=card><h2>Find an existing PD</h2><div class=toolbar><input id=pdSearch placeholder="PD number or role title"><button class=primary onclick="searchPDs()">Search</button><button onclick="showView('semantic')">Semantic search</button></div><div id=pdList class=pd-list></div></section><section id=detailContent><div class=card><h2>Select a PD</h2><p class=muted>Results will appear here with similar roles and mapping suggestions.</p></div></section></div>
</section>

<section id=semantic class=view>
<div class=hero><h1>Semantic Search</h1><p class=muted>Use this when you know the kind of work, but not the exact role title. The first search after restart may take a moment while the model loads.</p></div>
<section class=card><h2>Describe the role or work</h2><textarea id=query placeholder="e.g. creates reports, analyses data and communicates insights to stakeholders"></textarea><div class=toolbar><button class=primary onclick="runQuery()">Search roles and recommend job families</button></div></section>
<div id=semanticContent><section class=card><h2>Search results</h2><p class=muted>Your matching roles and mapping evidence will appear here.</p></section></div>
</section>

<section id=mapping class=view>
<div class=hero><h1>Mapping Assistant</h1><p class=muted>Use this for an unmapped or uncertain PD. The app shows similar mapped roles and recommended job family options, but the final decision remains human judgement.</p></div>
<div class=mapping-layout><section class="card mapping-picker"><h2>Choose a PD to map</h2><div class=toolbar><input id=mapSearch placeholder="Unmapped PD ID or role title"><button class=primary onclick="searchMapPDs()">Search</button></div><div id=mapList class=pd-list></div></section><section id=mappingContent><div class=card><h2>Select a PD</h2><p class=muted>Recommended job families, drill-down options and evidence roles will appear here.</p></div></section></div>
</section>

<section id=upload class=view>
<div class=hero><h1>Upload Position Description</h1><p class=muted>Turn a Word PD into a structured record, then continue to the separate validation workflow.</p></div>
<section class=card><h2>Upload Word PD</h2><p class=muted>Upload a `.docx` file. The app extracts it, saves the source file, and adds it to the validation queue.</p><input id=uploadFile type=file accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"><div class=toolbar><button class=primary onclick="uploadPD()">Upload and extract</button><a class=button href="http://127.0.0.1:8765/">Open Validation Queue</a></div><div id=uploadStatus class=muted></div></section>
</section>

<section id=workbook class=view>
<div class=hero><h1>Mapping Workbook Import</h1><p class=muted>Maintain the job-family framework and mapping reference data independently from classification administration.</p></div>
<section class=card><h2>Job family framework and mappings</h2><p class=muted>Upload the master mapping workbook when the framework or PD mappings are updated. This replaces the active import batch used by search and Mapping Assistant.</p><input id=jobFamilyFile type=file accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"><div class=toolbar><button class=primary onclick="uploadJobFamilyWorkbook()">Import workbook</button><button onclick="loadJobFamilyStatus()">Refresh status</button></div><div id=jobFamilyStatus class=muted>Loading current import status...</div></section>
</section>
<footer class=app-footer><div>Official Internal Workforce Tool</div><div class=footer-links><span>Privacy</span><span>Accessibility</span></div></footer>
</main></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});const text=await r.text();let j={};try{j=text?JSON.parse(text):{}}catch(e){throw new Error(`Server returned ${r.status}: ${text.slice(0,160)}`)}if(!r.ok)throw new Error(j.error||'Request failed');return j}
const viewAliases={search:'library','mapping-assistant':'mapping','mapping-workbook-import':'workbook'};
function showView(id,updateHash=true){id=viewAliases[id]||id;const view=document.getElementById(id);if(!view)id='home';document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===id));document.querySelectorAll('.nav [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===id||(id==='semantic'&&b.dataset.view==='library')));if(updateHash){const hash=id==='home'?'':id;history.replaceState(null,'',hash?'#'+hash:location.pathname+location.search)}}
window.addEventListener('hashchange',()=>showView(location.hash.slice(1)||'home',false));
function grade(row){const abbr=row.classification_abbreviation||'';const label=row.classification_display||row.classification_raw||row.classification_grade_band||'';const cohort=row.classification_cohort||'';if(!abbr&&!label)return '<span class=muted>Unclassified</span>';return `<span class=grade>${esc(abbr||label)}</span>${abbr&&label?`<br><span class=small>${esc(label)}</span>`:''}${cohort?`<br><span class=small>${esc(cohort)}</span>`:''}`}
function mapping(row){const code=row.primary_mapping_code||row.mapping_code,name=row.primary_mapping_name||row.mapping_name,level=row.primary_mapping_level||row.mapping_level;if(!code)return '<span class=muted>Unmapped</span>';const h=(row.mapping_hierarchy||[]).map(x=>`${esc(x.level)}: ${esc(x.name)}`).join('<br>');return `${esc(code)}<br>${esc(name)}<br><span class=muted>${esc(level)}</span>${h?`<div class=muted style="margin-top:5px">${h}</div>`:''}`}
let familyRankHints={};
let hierarchyFilters={};
let selectedGuideFamily={};
let selectedGuideSubfamily={};
let guideShortlists={};
let guideItemSets={};
let guideFamilyPages={};
let guidePositionIds={};
let guideSelectedAssignments={};
const GUIDE_MIN_SCORE=.30;
function suggestionFamilyRanks(suggestions){const ranks={};(suggestions||[]).forEach((s,i)=>{const jf=(s.hierarchy||[]).find(h=>h.level==='Job Family');if(jf&&jf.code&&ranks[jf.code]===undefined)ranks[jf.code]=i+1});return ranks}
function jobFamilyOptions(rows,id){const seen=new Map();rows.forEach(r=>{if(r.job_family_code)seen.set(r.job_family_code,r.job_family_name)});const ranks=familyRankHints[id]||{};return [...seen.entries()].sort((a,b)=>(ranks[a[0]]??9999)-(ranks[b[0]]??9999)||a[1].localeCompare(b[1]))}
function cohortOptions(rows){const seen=new Map();rows.forEach(r=>{if(r.classification_cohort)seen.set(r.classification_cohort,Number(r.classification_order??9999))});return [...seen.entries()].sort((a,b)=>a[1]-b[1]||a[0].localeCompare(b[0])).map(([name])=>name)}
function filterPanel(id,rows){const cohorts=cohortOptions(rows);if(!cohorts.length)return `<div id="${id}-hier-filter" class=small></div>`;return `<div class=filters id="${id}"><button onclick="clearFilters('${id}')">Clear filters</button><b>Optional grade/cohort filter</b><p class=small>Use this if you want the evidence roles to stay close to the role's classification level.</p>${cohorts.map(name=>`<label><input data-kind=cohort type=checkbox value="${esc(name)}" onchange="applyFilters('${id}')"> ${esc(name)}</label>`).join('')}<div id="${id}-hier-filter" class=small></div></div>`}
function filteredRows(id,rows){const families=[...document.querySelectorAll(`#${id} input[data-kind=family]:checked`)].map(x=>x.value);const cohorts=[...document.querySelectorAll(`#${id} input[data-kind=cohort]:checked`)].map(x=>x.value);const hierarchy=[...(hierarchyFilters[id]||[])];return rows.filter(r=>(!families.length||families.includes(r.job_family_code))&&(!cohorts.length||cohorts.includes(r.classification_cohort))&&(!hierarchy.length||(r.mapping_hierarchy||[]).some(h=>hierarchy.includes(h.code))))}
function similarTable(rows){return `<table><thead><tr><th>Similarity</th><th>PD</th><th>Role</th><th>Grade</th><th>Primary mapping</th><th>Validated</th></tr></thead><tbody>${rows.slice(0,10).map(r=>`<tr><td>${Number(r.similarity).toFixed(3)}</td><td>${esc(r.position_description_no)}</td><td>${esc(r.role_title)}</td><td>${grade(r)}</td><td>${mapping(r)}</td><td>${esc(r.mapping_validated)}</td></tr>`).join('')}</tbody></table>`}
let resultSets={};
function evidenceScore(similarities,validated,evidence){const ordered=[...similarities].sort((a,b)=>b-a);if(!ordered.length)return {score:0,best:0,avgTop3:0,validationSignal:0,evidenceSignal:0};const best=ordered[0];const avgTop3=ordered.slice(0,3).reduce((a,b)=>a+b,0)/Math.min(3,ordered.length);const validationSignal=evidence?validated/evidence:0;const evidenceSignal=Math.max(0,Math.min(evidence,3)-1)/2;const score=.25*best+.60*avgTop3+.03*validationSignal+.12*evidenceSignal;return {score,best,avgTop3,validationSignal,evidenceSignal}}
function rollupHierarchy(rows,frameworkScores={}){const groups={};(rows||[]).forEach(r=>{const validated=['yes','validated','true','y'].includes(String(r.mapping_validated||'').trim().toLowerCase());const hierarchy=r.mapping_hierarchy||[];hierarchy.forEach((h,idx)=>{if(!h.code)return;const key=h.level+'|'+h.code;const fw=frameworkScores[h.code]||{};const parentCode=fw.parent_code||h.parent_code||(idx>0?hierarchy[idx-1].code:'');if(!groups[key])groups[key]={...h,parent_code:parentCode,main_definition:fw.main_definition||'',supp_definition_1:fw.supp_definition_1||'',supp_definition_2:fw.supp_definition_2||'',exclusions:fw.exclusions||'',score:0,evidenceScore:0,frameworkSimilarity:Number(fw.framework_similarity||0),evidence:0,validated:0,best:0,avgTop3:0,path:hierarchy.slice(0,idx+1).map(x=>x.name).join(' > '),family_code:(hierarchy.find(x=>levelMatches(x.level,['job family']))||{}).code||'',similarities:[]};groups[key].similarities.push(Number(r.similarity||0));groups[key].evidence+=1;groups[key].validated+=validated?1:0})});Object.values(groups).forEach(g=>{const s=evidenceScore(g.similarities,g.validated,g.evidence);g.evidenceScore=s.score;g.best=s.best;g.avgTop3=s.avgTop3;g.frameworkSimilarity=Number(frameworkScores[g.code]?.framework_similarity||0);g.score=.80*g.evidenceScore+.20*g.frameworkSimilarity});return Object.values(groups).sort((a,b)=>b.score-a.score||b.best-a.best)}
function levelMatches(level,terms){const l=String(level||'').toLowerCase();return terms.some(t=>l.includes(t))}
function rankedFamilies(rolled,suggestions){return rolled.filter(x=>levelMatches(x.level,['job family'])).slice(0,4)}
function topSubfamilies(rolled,familyCode){return rolled.filter(x=>x.family_code===familyCode&&levelMatches(x.level,['sub'])&&Number(x.score||0)>=GUIDE_MIN_SCORE).slice(0,3)}
function specialisationsForSubfamily(rolled,sub){if(!sub)return [];return rolled.filter(x=>x.family_code===sub.family_code&&!levelMatches(x.level,['job family','sub'])&&Number(x.score||0)>=GUIDE_MIN_SCORE&&(x.parent_code===sub.code||String(x.path||'').includes(sub.name))).slice(0,3)}
function guideBrief(item){return `score ${Number(item.score||0).toFixed(3)} | evidence ${Number(item.evidenceScore||0).toFixed(3)} | framework ${Number(item.frameworkSimilarity||0).toFixed(3)} | ${Number(item.validated||0)} validated`}
function frameworkDescription(item){return String(item.main_definition||item.supp_definition_1||item.supp_definition_2||'').trim()}
function rememberGuideItems(id,rolled){guideItemSets[id]={};rolled.forEach(x=>{guideItemSets[id][x.code]=x})}
function iconForFamily(name){const n=(name||'').toLowerCase();if(n.includes('technology'))return '⌨';if(n.includes('project'))return '▦';if(n.includes('legal'))return '⚖';if(n.includes('business'))return '▣';if(n.includes('analytics'))return '⌕';return '◇'}
function familyChoices(id,families){const visible=families.slice(0,4);const selected=selectedGuideFamily[id]||visible[0]?.code||'';if(!selectedGuideFamily[id]&&visible[0])selectedGuideFamily[id]=visible[0].code;return `<p class=small>Showing the four highest-ranked job families.</p><div class=family-choices>${visible.map((item,i)=>`<button class="family-option ${selected===item.code?'active':''}" onclick="selectGuideFamily('${id}','${esc(item.code)}')"><span class=family-icon>${iconForFamily(item.name)}</span><span><span class=family-name>${esc(item.name)}</span><span class=family-meta>Suggestion ${i+1} · ${Number(item.validated||0)} validated evidence roles</span>${frameworkDescription(item)?`<span class=family-description>${esc(frameworkDescription(item))}</span>`:''}</span><span class=radio-dot></span></button>`).join('')}</div>`}
function subfamilyList(id,rolled,family){if(!family)return '<div class=empty-panel>Select a job family first.</div>';const selected=selectedGuideSubfamily[id]||{};const subs=topSubfamilies(rolled,family.code);const familyAction=`<div class=toolbar><button onclick="markForReview('${id}','${esc(family.code)}')">Shortlist ${esc(family.name)} at job-family level</button></div>`;if(!subs.length)return `<div class=empty-panel>No sub-family meets the current scoring threshold.</div>${familyAction}`;if(!selected.code&&subs[0])selectedGuideSubfamily[id]={code:subs[0].code,column:0};return `<div class=subfamily-list>${subs.map((s,i)=>`<button class="subfamily-row ${(selectedGuideSubfamily[id]||{}).code===s.code?'active':''}" onclick="openSpecialisations('${id}','${esc(s.code)}',0)"><span><b>${esc(s.name)}</b><span class=family-meta>#${i+1} under ${esc(family.name)} · ${guideBrief(s)}</span></span><span class=chevron>›</span></button>`).join('')}</div>${familyAction}`}
function specialisationList(id,rolled){const selected=selectedGuideSubfamily[id];if(!selected||!selected.code)return '<div class=empty-panel>Select a sub-family to see possible specialisations.</div>';const sub=(guideItemSets[id]||{})[selected.code];if(!sub)return '<div class=empty-panel>Select a sub-family to see possible specialisations.</div>';const specs=specialisationsForSubfamily(rolled,sub);const cards=specs.length?specs.map(s=>`<article class=specialisation-card><div><h4>${esc(s.name)}</h4><p>${esc(s.level)} · ${esc(s.path||'')}</p>${frameworkDescription(s)?`<p>${esc(frameworkDescription(s))}</p>`:''}</div><button onclick="markForReview('${id}','${esc(s.code)}')">Shortlist</button></article>`).join(''):`<div class=empty-panel>No specialisations under ${esc(sub.name)} meet the threshold yet. You can still shortlist the sub-family.</div>`;return `<div class=specialisation-list>${cards}<article class=specialisation-card><div><h4>${esc(sub.name)}</h4><p>Assign at sub-family level without selecting a specialisation.</p>${frameworkDescription(sub)?`<p>${esc(frameworkDescription(sub))}</p>`:''}</div><button onclick="markForReview('${id}','${esc(sub.code)}')">Shortlist</button></article></div>`}
function shortlistBar(id){const codes=guideShortlists[id]||[];if(!codes.length)return `<div id="${id}-review-detail"></div>`;const items=codes.map(code=>(guideItemSets[id]||{})[code]).filter(Boolean);const names=items.map(x=>x.name).join(', ');return `<div id="${id}-review-detail"></div><div class=shortlist-bar><div class=shortlist-icon>✓</div><div><div class=shortlist-title>Shortlist (${items.length})</div><div class=shortlist-items>${esc(names)}</div></div><button onclick="openShortlistReview('${id}')">Review shortlist</button><button class=shortlist-close title="Clear shortlist" onclick="clearShortlist('${id}')">×</button></div>`}
function mappingRail(){return `<aside class=mapping-rail><div><h3>Mapping progress</h3><div class="mapping-step done"><span class=step-dot>✓</span><span><span class=step-title>Review PD</span><br><span class=step-state>Validated</span></span></div><div class="mapping-step active"><span class=step-dot>2</span><span><span class=step-title>Classify Family</span><br><span class=step-state>In progress</span></span></div><div class=mapping-step><span class=step-dot>3</span><span><span class=step-title>Evidence Review</span><br><span class=step-state>Pending</span></span></div></div><div class=mapping-guide-note><div><b>Mapping guide</b><br>Select the best-fit family based on the PD's core purpose, duties, framework definitions and similar validated roles.</div></div></aside>`}
function decisionGuide(id,rows,suggestions=[],frameworkScores={}){const rolled=rollupHierarchy(rows,frameworkScores);rememberGuideItems(id,rolled);const families=rankedFamilies(rolled,suggestions);if(!families.length)return '';const selectedFamily=(guideItemSets[id]||{})[selectedGuideFamily[id]]||families[Math.min(Number(guideFamilyPages[id]||0),families.length-1)]||families[0];selectedGuideFamily[id]=selectedFamily.code;return `<section id="${id}-guide" class=decision-guide><div class=section-head><div><h2>Select Job Family</h2></div><span class=suggested-note>ⓘ Suggested using similar roles, definitions and grade proximity</span></div>${familyChoices(id,families)}<div class=drill-grid><section><p class=drill-label>Select sub-family</p>${subfamilyList(id,rolled,selectedFamily)}</section><section><p class=drill-label>Refine specialisation</p>${specialisationList(id,rolled)}</section></div>${shortlistBar(id)}</section>`}
function redrawGuide(id){const scoreSets=window.frameworkScoreSets||{};const container=document.querySelector(`#${id}-guide`);if(container)container.outerHTML=decisionGuide(id,resultSets[id]||[],[],scoreSets[id]||{})}
function resultBlock(id,heading,rows,suggestions=[],frameworkScores={}){resultSets[id]=rows;familyRankHints[id]=suggestionFamilyRanks(suggestions);hierarchyFilters[id]=new Set();selectedGuideFamily[id]='';selectedGuideSubfamily[id]=null;guideFamilyPages[id]=0;guideShortlists[id]=[];guideSelectedAssignments[id]=new Set();window.frameworkScoreSets=window.frameworkScoreSets||{};window.frameworkScoreSets[id]=frameworkScores||{};const isMapping=id.includes('mappingContent');const filters=isMapping?'':filterPanel(id,rows);return `${decisionGuide(id,rows,suggestions,frameworkScores)}<div class=evidence-heading><h2>${esc(heading)}</h2><span class=small>Evidence updates when you select or shortlist a framework option.</span></div>${filters}<div id="${id}-table">${similarTable(rows)}</div><p class=muted>Showing top 10 of <span id="${id}-count">${rows.length}</span> matching roles after filters.</p>`}
function applyFilters(id){const rows=filteredRows(id,resultSets[id]||[]);document.querySelector(`#${id}-table`).innerHTML=similarTable(rows);document.querySelector(`#${id}-count`).textContent=rows.length;const label=document.querySelector(`#${id}-hier-filter`);const active=[...(hierarchyFilters[id]||[])];if(label)label.innerHTML=active.length?`Framework drill-down active: ${active.map(esc).join(', ')}`:''}
function toggleHierarchyFilter(id,code){if(!hierarchyFilters[id])hierarchyFilters[id]=new Set();hierarchyFilters[id].has(code)?hierarchyFilters[id].delete(code):hierarchyFilters[id].add(code);applyFilters(id)}
function setHierarchyFilter(id,code){hierarchyFilters[id]=new Set([code]);applyFilters(id)}
function openSpecialisations(id,code,column){selectedGuideSubfamily[id]={code,column};redrawGuide(id);setHierarchyFilter(id,code)}
function closeSpecialisations(id){selectedGuideSubfamily[id]=null;redrawGuide(id)}
function pageFamilies(id,delta){guideFamilyPages[id]=Math.max(0,Number(guideFamilyPages[id]||0)+delta);selectedGuideFamily[id]='';selectedGuideSubfamily[id]=null;redrawGuide(id)}
function markForReview(id,code){if(!guideShortlists[id])guideShortlists[id]=[];if(!guideShortlists[id].includes(code))guideShortlists[id].push(code);redrawGuide(id);showReviewDetail(id,code)}
function showReviewDetail(id,code){const item=(guideItemSets[id]||{})[code];const target=document.querySelector(`#${id}-review-detail`);if(!item||!target)return;setHierarchyFilter(id,code);target.innerHTML=`<div class=review-detail><span class=guide-score>${Number(item.score||0).toFixed(3)}</span><h3>${esc(item.name)}</h3><p><b>${esc(item.level)}</b>${item.path?`<br><span class=muted>${esc(item.path)}</span>`:''}</p><p class=muted>${guideBrief(item)}</p><p class=small>Evidence roles below are now filtered to this shortlisted option.</p><div class=toolbar><button disabled>Assign mapping - next step</button></div></div>`}
function shortlistReviewHtml(id){const codes=guideShortlists[id]||[];const chosen=guideSelectedAssignments[id]||new Set();const items=codes.map(code=>(guideItemSets[id]||{})[code]).filter(Boolean);return `<section class=shortlist-review><div class=shortlist-review-head><div><h3>Review shortlist</h3><p class=muted>Select one, two or three mappings to assign to this PD.</p></div><span id="${id}-selection-count" class=selection-count>${chosen.size} selected</span></div><div class=shortlist-review-list>${items.map(item=>`<label class=shortlist-review-option><input type=checkbox value="${esc(item.code)}" ${chosen.has(item.code)?'checked':''} onchange="toggleAssignmentSelection('${id}',this)"><span><h4>${esc(item.name)}</h4><p><b>${esc(item.level)}</b> · ${esc(item.path||'')}</p>${frameworkDescription(item)?`<p>${esc(frameworkDescription(item))}</p>`:''}<p>${guideBrief(item)}</p></span><button type=button class=remove-shortlist onclick="event.preventDefault();removeFromShortlist('${id}','${esc(item.code)}')">Remove</button></label>`).join('')}</div><div class=shortlist-review-actions><span id="${id}-assignment-status" class=assignment-status>Choose up to three mappings.</span><button onclick="closeShortlistReview('${id}')">Back</button><button id="${id}-assign-button" class=primary ${chosen.size<1||chosen.size>3?'disabled':''} onclick="assignSelectedMappings('${id}')">Assign mappings</button></div></section>`}
function openShortlistReview(id){const codes=guideShortlists[id]||[];if(!codes.length)return;guideSelectedAssignments[id]=new Set();const target=document.querySelector(`#${id}-review-detail`);if(target){target.innerHTML=shortlistReviewHtml(id);target.scrollIntoView({behavior:'smooth',block:'start'})}}
function closeShortlistReview(id){guideSelectedAssignments[id]=new Set();const target=document.querySelector(`#${id}-review-detail`);if(target)target.innerHTML=''}
function toggleAssignmentSelection(id,input){if(!guideSelectedAssignments[id])guideSelectedAssignments[id]=new Set();const chosen=guideSelectedAssignments[id];if(input.checked&&chosen.size>=3){input.checked=false;const status=document.querySelector(`#${id}-assignment-status`);if(status)status.textContent='A maximum of three mappings can be assigned.';return}input.checked?chosen.add(input.value):chosen.delete(input.value);const count=document.querySelector(`#${id}-selection-count`);if(count)count.textContent=`${chosen.size} selected`;const button=document.querySelector(`#${id}-assign-button`);if(button)button.disabled=chosen.size<1||chosen.size>3;const status=document.querySelector(`#${id}-assignment-status`);if(status)status.textContent=chosen.size?`${chosen.size} mapping${chosen.size===1?'':'s'} ready to assign.`:'Choose at least one mapping.'}
function removeFromShortlist(id,code){guideShortlists[id]=(guideShortlists[id]||[]).filter(x=>x!==code);if(guideSelectedAssignments[id])guideSelectedAssignments[id].delete(code);redrawGuide(id);if((guideShortlists[id]||[]).length)openShortlistReview(id)}
async function assignSelectedMappings(id){const selected=guideSelectedAssignments[id]||new Set();const chosen=(guideShortlists[id]||[]).filter(code=>selected.has(code));const pdId=guidePositionIds[id];const status=document.querySelector(`#${id}-assignment-status`);const button=document.querySelector(`#${id}-assign-button`);if(!pdId||chosen.length<1||chosen.length>3)return;if(status)status.textContent='Saving mappings...';if(button)button.disabled=true;try{const result=await api(`/api/pds/${pdId}/assign-mappings`,{method:'POST',body:JSON.stringify({mapping_codes:chosen})});if(status)status.textContent=`Saved ${result.mappings.length} mapping${result.mappings.length===1?'':'s'}.`;const target=document.querySelector(`#${id}-review-detail`);if(target)target.innerHTML=`<div class=assign-success>Mappings assigned successfully. Refreshing the PD...</div>`;setTimeout(()=>loadPD(pdId,'mappingContent'),650)}catch(err){if(status)status.textContent=err.message||err;if(button)button.disabled=false}}
function clearShortlist(id){guideShortlists[id]=[];guideSelectedAssignments[id]=new Set();redrawGuide(id)}
function selectGuideFamily(id,code){selectedGuideFamily[id]=code;selectedGuideSubfamily[id]=null;redrawGuide(id);setHierarchyFilter(id,code)}
function clearFilters(id){document.querySelectorAll(`#${id} input`).forEach(x=>x.checked=false);hierarchyFilters[id]=new Set();applyFilters(id)}
function suggestionsHtml(rows){if(!rows.length)return '<p class=muted>No mapping suggestions available.</p>';return rows.map(s=>{const hier=(s.hierarchy||[]).map(h=>`${esc(h.level)}: ${esc(h.name)} <span class=muted>(${esc(h.code)})</span>`).join(' -> ');const ev=(s.evidence||[]).slice(0,6).map(e=>`<li>${esc(e.position_description_no)} - ${esc(e.role_title)} <span class=muted>(${Number(e.similarity).toFixed(3)}, validated: ${esc(e.mapping_validated)})</span></li>`).join('');return `<div class=suggestion><div class=confidence>${esc(s.confidence)}</div><h3>${esc(s.mapping_code)} - ${esc(s.mapping_name)}</h3><div><b>Hierarchy:</b> ${hier||'<span class=muted>Not found</span>'}</div><p class=muted>${esc(s.mapping_level)} - weighted score ${Number(s.weighted_score).toFixed(3)} - ${s.evidence_count} evidence roles - ${s.validated_evidence_count} validated</p><ul>${ev}</ul></div>`}).join('')}
async function searchPDs(){const q=document.querySelector('#pdSearch').value;const rows=await api('/api/pds?q='+encodeURIComponent(q));document.querySelector('#pdList').innerHTML=pdButtons(rows,'detailContent')||'<p class=muted>No matches.</p>'}
async function searchMapPDs(){const q=document.querySelector('#mapSearch').value;const rows=await api('/api/pds?q='+encodeURIComponent(q));document.querySelector('#mapList').innerHTML=pdButtons(rows,'mappingContent')||'<p class=muted>No matches.</p>'}
function pdButtons(rows,target){return rows.map(r=>target==='mappingContent'?`<button class=pd-btn onclick="window.location.href='/mapping-assistant?pd=${r.id}'">${esc(r.position_description_no)} - ${esc(r.role_title)}<small>${esc(r.classification_abbreviation||r.classification_display||r.classification_grade_band||'No grade')} | ${esc(r.mapping_name||'Unmapped')}</small></button>`:`<button class=pd-btn onclick="loadPD(${r.id},'${target}')">${esc(r.position_description_no)} - ${esc(r.role_title)}<small>${esc(r.classification_abbreviation||r.classification_display||r.classification_grade_band||'No grade')} | ${esc(r.mapping_name||'Unmapped')}</small></button>`).join('')}
function assignedMappingsHtml(rows){if(!rows||!rows.length)return '';return `<div class=assigned-summary><b>Assigned mappings</b><ol class=assigned-list>${rows.map(row=>`<li>${esc(row.mapping_name)} <span class=muted>(${esc(row.mapping_level)} · ${esc(row.mapping_code)})</span></li>`).join('')}</ol></div>`}
async function loadPD(id,target){document.querySelector('#'+target).innerHTML='<section class=card><h2>Loading...</h2></section>';try{const data=await api('/api/pds/'+id+'/intelligence');const d=data.pd;const guideId=target+'-similar';guidePositionIds[guideId]=id;const summary=target==='mappingContent'?`<section class=assist-summary><div><div class=assist-title-row><span class=pd-chip>PD ${esc(d.position_description_no)}</span><h2>${esc(d.role_title)}</h2></div><div class=meta><span>${grade(d)}</span><span>${esc(d.source_filename)}</span></div>${assignedMappingsHtml(data.assigned_mappings||[])}</div><div class=validation-badge>${(data.assigned_mappings||[]).length?'✓ Mapped':d.mapping_validated?'✓ '+esc(d.mapping_validated):'Mapping in progress'}</div></section>`:`<section class=card><h2>${esc(d.position_description_no)} - ${esc(d.role_title)}</h2><p class=muted>${grade(d)}<br>${esc(d.source_filename)}</p>${assignedMappingsHtml(data.assigned_mappings||[])}</section>`;const body=`${summary}${resultBlock(guideId,'Similar Roles for Context',data.similar_roles||[],data.mapping_suggestions||[],data.framework_scores||{})}`;document.querySelector('#'+target).innerHTML=target==='mappingContent'?`<div class=mapping-workflow>${mappingRail()}<main class=mapping-main>${body}</main></div>`:`<section class=card>${body}</section>`}catch(err){const msg=String(err.message||err);const prepare=msg.includes('No embedding found')?`<p><button class=primary onclick="preparePD(${id},'${target}')">Prepare intelligence for this PD</button></p><p class=muted>This creates mapping text and an embedding so the Mapping Assistant can compare the PD.</p>`:'';document.querySelector('#'+target).innerHTML=`<section class=card><h2>Could not load PD</h2><p class=muted>${esc(msg)}</p>${prepare}</section>`}}
async function preparePD(id,target){document.querySelector('#'+target).innerHTML='<section class=card><h2>Preparing intelligence...</h2><p class=muted>This may take a moment while the embedding model runs.</p></section>';try{await api('/api/pds/'+id+'/prepare-intelligence',{method:'POST',body:'{}'});await loadPD(id,target)}catch(err){document.querySelector('#'+target).innerHTML=`<section class=card><h2>Preparation failed</h2><p class=muted>${esc(err.message||err)}</p></section>`}}
async function runQuery(){const q=document.querySelector('#query').value.trim();if(!q)return;document.querySelector('#semanticContent').innerHTML='<section class=card><h2>Searching...</h2><p class=muted>The first search may take a moment while the model loads.</p></section>';try{const data=await api('/api/search?query='+encodeURIComponent(q));document.querySelector('#semanticContent').innerHTML=`<section class=card><h2>Search results</h2><p class=muted>${esc(q)}</p></section><section class=card>${resultBlock('query-results','Evidence roles',data.roles||[],data.mapping_suggestions||[],data.framework_scores||{})}</section>`}catch(err){document.querySelector('#semanticContent').innerHTML=`<section class=card><h2>Search failed</h2><p class=muted>${esc(err.message||err)}</p></section>`}}
function arrayBufferToBase64(buffer){let binary='';const bytes=new Uint8Array(buffer);const chunk=0x8000;for(let i=0;i<bytes.length;i+=chunk){binary+=String.fromCharCode.apply(null,bytes.subarray(i,i+chunk))}return btoa(binary)}
async function uploadPD(){const file=document.querySelector('#uploadFile').files[0];const status=document.querySelector('#uploadStatus');if(!file){status.textContent='Choose a .docx file first.';return}if(!file.name.toLowerCase().endsWith('.docx')){status.textContent='Only .docx Word files are supported in this prototype.';return}status.textContent='Uploading and extracting...';try{const content_base64=arrayBufferToBase64(await file.arrayBuffer());const result=await api('/api/import-pd',{method:'POST',body:JSON.stringify({filename:file.name,content_base64})});status.innerHTML=`Imported <b>${esc(result.role_title)}</b>. <a href="http://127.0.0.1:8765/?pd=${result.position_description_id}">Open for validation</a>`;await loadValidationQueue();await searchPDs()}catch(err){status.textContent=err.message||err}}
function jobFamilySummaryHtml(s){if(!s||!s.has_active_import)return '<p class=muted>No job family workbook has been imported yet.</p>';return `<p><b>Active workbook:</b> ${esc(s.source_filename)}<br><span class=small>Imported ${esc(s.imported_at||'')}</span></p><table><tbody><tr><th>Framework rows</th><td>${esc(s.framework_rows)}</td></tr><tr><th>Mapping rows</th><td>${esc(s.mapping_rows)}</td></tr><tr><th>Distinct workbook PD IDs mapped</th><td>${esc(s.distinct_workbook_pd_ids)}</td></tr><tr><th>Distinct workbook PD IDs validated</th><td>${esc(s.distinct_validated_workbook_pd_ids)}</td></tr><tr><th>Linked database PD records</th><td>${esc(s.distinct_linked_db_pds)}</td></tr><tr><th>Linked validated database PD records</th><td>${esc(s.distinct_validated_linked_db_pds)}</td></tr><tr><th>Linked mapping rows</th><td>${esc(s.mapping_rows_linked_to_pds)}</td></tr><tr><th>Unlinked mapping rows</th><td>${esc(s.unlinked_mapping_rows)}</td></tr><tr><th>Invalid mapping codes</th><td>${esc(s.invalid_mapping_codes)}</td></tr></tbody></table><p class=small>Mappings link by the five-digit PD base number, so a workbook PD ID like 11417 can match database versions like 11417-01.</p>`}
async function loadJobFamilyStatus(){const target=document.querySelector('#jobFamilyStatus');if(!target)return;target.innerHTML='<p class=muted>Loading current import status...</p>';try{const data=await api('/api/job-family-import-status');target.innerHTML=jobFamilySummaryHtml(data)}catch(err){target.innerHTML=`<p class=muted>Could not load import status: ${esc(err.message||err)}</p>`}}
async function uploadJobFamilyWorkbook(){const file=document.querySelector('#jobFamilyFile').files[0];const status=document.querySelector('#jobFamilyStatus');if(!file){status.textContent='Choose an .xlsx workbook first.';return}if(!file.name.toLowerCase().endsWith('.xlsx')){status.textContent='Only .xlsx Excel workbooks are supported.';return}status.textContent='Uploading and importing workbook...';try{const content_base64=arrayBufferToBase64(await file.arrayBuffer());const result=await api('/api/import-job-family-workbook',{method:'POST',body:JSON.stringify({filename:file.name,content_base64})});status.innerHTML=`<p><b>Import complete.</b></p>${jobFamilySummaryHtml(result.status)}`;await searchPDs()}catch(err){status.textContent=err.message||err}}
async function loadValidationQueue(){const target=document.querySelector('#validationQueue');if(!target)return;target.innerHTML='<p class=muted>Loading queue...</p>';try{const data=await api('/api/validation-queue');const rows=data.rows||[];if(!rows.length){target.innerHTML='<p class=muted>No unvalidated PDs in the queue.</p>';return}const shown=rows.slice(0,100);target.innerHTML=`<p class=muted>${rows.length} unvalidated PDs. Showing the most recently updated ${shown.length}.</p><table><thead><tr><th>PD</th><th>Role</th><th>Validation</th><th>Intelligence</th><th>Issues</th><th>Action</th></tr></thead><tbody>${shown.map(r=>`<tr><td>${esc(r.position_description_no||'')}</td><td>${esc(r.role_title)}<br><span class=small>${esc(r.source_filename)}</span></td><td>${esc(r.validation_status)}<br><span class=small>${esc(r.extraction_status)}</span></td><td>${esc(r.intelligence_status||'Not prepared')}</td><td>${esc(r.issue_count)}</td><td><a class=button href="http://127.0.0.1:8765/?pd=${r.id}">Review</a></td></tr>`).join('')}</tbody></table>`}catch(err){target.innerHTML=`<p class=muted>Could not load queue: ${esc(err.message||err)}</p>`}}
showView(location.hash.slice(1)||'home',false);
loadValidationQueue();
loadJobFamilyStatus();
searchPDs();
</script></body></html>"""


ADMIN_HTML = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Classification admin</title>
<style>
:root{--purple:#481579;--ink:#172033;--muted:#667085;--line:#d7dce6;--bg:#f4f6fa;--green:#067647}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 system-ui,Segoe UI,sans-serif}.system-nav{background:white;border-bottom:1px solid var(--line);padding:0 28px;display:flex;align-items:center;justify-content:space-between}.system-brand{font-size:17px;font-weight:800;color:#082646;text-decoration:none;white-space:nowrap}.system-links{display:flex;gap:20px;align-items:center}.system-links a{border:0;border-bottom:3px solid transparent;border-radius:0;padding:18px 0 14px;color:var(--muted);white-space:nowrap}.system-links a:hover,.system-links a.active{color:var(--purple);border-bottom-color:var(--purple)}main{padding:24px;max-width:1500px;margin:auto}.card{background:white;border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px}h1{color:#351052;margin:0 0 6px}a,button{border:1px solid var(--purple);background:white;color:var(--purple);padding:8px 12px;border-radius:9px;text-decoration:none;cursor:pointer;font-weight:650}button.primary{background:var(--purple);color:white}.toolbar{display:flex;gap:10px;align-items:center;margin:14px 0}.muted{color:var(--muted)}table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #dde1e9;padding:7px;text-align:left;vertical-align:top}th{background:#f2ecf7;color:#481579;position:sticky;top:0}input,textarea{width:100%;border:1px solid #c8cfda;border-radius:7px;padding:7px;font:inherit}textarea{min-height:38px}.num{width:82px}.raw{min-width:220px}.count{text-align:right}.status{font-weight:700;color:var(--green)}@media(max-width:1000px){.system-nav{align-items:flex-start;flex-direction:column;padding-top:14px}.system-links{flex-wrap:wrap;gap:8px 16px}.system-links a{padding:8px 0}}
</style></head><body><nav class=system-nav><a class=system-brand href="/">PD Manager</a><div class=system-links><a href="/#upload">Upload</a><a href="http://127.0.0.1:8765/">Validation Queue</a><a href="/#library">Search</a><a href="/mapping-assistant">Mapping Assistant</a><a class=active href="/admin/classifications">Classification Admin</a><a href="/#workbook">Mapping Workbook Import</a></div></nav><main>
<section class=card>
<h1>Classification admin</h1>
<p class=muted>Edit the grade labels used by search and filtering. The raw label is what came from the PD; the display label, abbreviation, cohort and order are the governed reference values.</p>
<div class=toolbar><button class=primary onclick="save()">Save changes</button><a href="/api/classifications/export?format=csv">Export CSV</a><a href="/api/classifications/export?format=json">Export JSON</a><span id=status class=status></span></div>
</section>
<section class=card><div id=table>Loading...</div></section>
</main><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let rows=[];
async function load(){const r=await fetch('/api/classifications');const j=await r.json();rows=j.rows||[];render()}
function cell(i,name,cls=''){const v=rows[i][name]??'';return `<input class="${cls}" data-i="${i}" data-name="${name}" value="${esc(v)}">`}
function render(){document.querySelector('#table').innerHTML=`<table><thead><tr><th>Raw label</th><th>PDs</th><th>Display label</th><th>Abbrev</th><th>Cohort</th><th>Order</th><th>EA / source</th><th>Active</th><th>Notes</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td class=raw>${esc(r.raw_label)}</td><td class=count>${esc(r.usage_count)}</td><td>${cell(i,'display_label')}</td><td>${cell(i,'abbreviation')}</td><td>${cell(i,'cohort')}</td><td>${cell(i,'seniority_order','num')}</td><td>${cell(i,'enterprise_agreement')}</td><td><input type=checkbox data-i="${i}" data-name=active ${r.active?'checked':''}></td><td><textarea data-i="${i}" data-name=notes>${esc(r.notes)}</textarea></td></tr>`).join('')}</tbody></table>`}
function collect(){document.querySelectorAll('[data-i]').forEach(el=>{const i=Number(el.dataset.i), name=el.dataset.name;rows[i][name]=el.type==='checkbox'?(el.checked?1:0):el.value});return rows}
async function save(){document.querySelector('#status').textContent='Saving...';const r=await fetch('/api/classifications',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:collect()})});const j=await r.json();if(!r.ok){document.querySelector('#status').textContent=j.error||'Save failed';return}document.querySelector('#status').textContent=`Saved ${j.updated} rows`;await load()}
load();
</script></body></html>"""


def make_handler(database_path: Path, model_name: str):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, value: object, status: int = 200) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, value: str, status: int = 200) -> None:
            body = value.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location: str) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _download(self, body: bytes, filename: str, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> object:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            return json.loads(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)
            try:
                if path == "/":
                    self._html(HTML_V2)
                    return
                if path == "/career-explorer":
                    with connect_database(database_path) as connection:
                        route_payload, constellation_payload = build_reference_payloads(connection)
                        self._html(render_career_explorer(route_payload, constellation_payload))
                    return
                if path == "/api/career-explorer/neighbours":
                    role_id = params.get("role_id", [""])[0].strip()
                    try:
                        cursor = int(params.get("cursor", ["0"])[0])
                    except ValueError:
                        self._json({"error": "cursor must be an integer"}, 400)
                        return
                    anchored = tuple(
                        item.strip()
                        for value in params.get("anchored", [])
                        for item in value.split(",")
                        if item.strip()
                    )
                    with connect_database(database_path) as connection:
                        try:
                            payload = career_explorer_neighbours(
                                connection,
                                role_id,
                                cursor=cursor,
                                anchored_role_ids=anchored,
                            )
                        except KeyError:
                            self._json({"error": "Role not found"}, 404)
                            return
                    self._json(payload)
                    return
                if path == "/mapping-assistant":
                    requested_pd = params.get("pd", [""])[0]
                    with connect_database(database_path) as connection:
                        pd_id = resolve_pd_identifier(connection, requested_pd)
                        if pd_id is None:
                            self._redirect("/#mapping")
                            return
                        detail = pd_detail(connection, pd_id)
                        if detail is None:
                            self._json({"error": "Not found"}, 404)
                            return
                        similar = find_similar_roles(connection, pd_id, model_name=model_name, limit=50)
                        framework_scores = framework_similarity_scores_for_pd(
                            connection,
                            pd_id,
                            model_name=model_name,
                        )
                        similar_json = _similar_json(connection, similar)
                        assigned_mappings = job_family_mappings_for_pd(connection, pd_id)
                        payload = build_mapping_assistant_payload(
                            connection,
                            detail,
                            assigned_mappings,
                            similar_json,
                            framework_scores,
                        )
                    self._html(render_mapping_assistant(payload))
                    return
                if path == "/admin/classifications":
                    self._html(ADMIN_HTML)
                    return
                if path == "/api/version":
                    self._json({"version": APP_VERSION, "model": model_name})
                    return
                if path == "/api/classifications":
                    with connect_database(database_path) as connection:
                        self._json({"rows": classification_rows(connection)})
                    return
                if path == "/api/classifications/export":
                    export_format = params.get("format", ["csv"])[0].lower()
                    with connect_database(database_path) as connection:
                        rows = classification_rows(connection)
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    if export_format == "json":
                        body = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
                        self._download(
                            body,
                            f"classification-references-{stamp}.json",
                            "application/json; charset=utf-8",
                        )
                    else:
                        self._download(
                            _classifications_csv(rows),
                            f"classification-references-{stamp}.csv",
                            "text/csv; charset=utf-8",
                        )
                    return
                if path == "/api/validation-queue":
                    with connect_database(database_path) as connection:
                        self._json({"rows": validation_queue(connection)})
                    return
                if path == "/api/job-family-import-status":
                    with connect_database(database_path) as connection:
                        self._json(job_family_import_status(connection))
                    return
                if path == "/api/pds":
                    query = params.get("q", [""])[0]
                    with connect_database(database_path) as connection:
                        self._json(search_pds(connection, query))
                    return
                if path.startswith("/api/pds/") and path.endswith("/intelligence"):
                    pd_id = int(path.split("/")[3])
                    with connect_database(database_path) as connection:
                        detail = pd_detail(connection, pd_id)
                        if detail is None:
                            self._json({"error": "Not found"}, 404)
                            return
                        similar = find_similar_roles(connection, pd_id, model_name=model_name, limit=50)
                        suggestions = suggest_mappings_for_pd(connection, pd_id, model_name=model_name)
                        framework_scores = framework_similarity_scores_for_pd(
                            connection,
                            pd_id,
                            model_name=model_name,
                        )
                        similar_json = _similar_json(connection, similar)
                        assigned_mappings = job_family_mappings_for_pd(connection, pd_id)
                    self._json({
                        "pd": detail,
                        "assigned_mappings": assigned_mappings,
                        "similar_roles": similar_json,
                        "mapping_suggestions": _to_jsonable(suggestions),
                        "framework_scores": framework_scores,
                    })
                    return
                if path == "/api/search":
                    query = params.get("query", [""])[0].strip()
                    if not query:
                        self._json({"error": "Missing query"}, 400)
                        return
                    with connect_database(database_path) as connection:
                        model = _embedder(model_name)
                        roles = search_roles(connection, query, model, model_name=model_name, limit=50)
                        suggestions = suggest_mappings_for_query(connection, query, model, model_name=model_name)
                        framework_scores = framework_similarity_scores_for_query(
                            connection,
                            query,
                            model,
                            model_name=model_name,
                        )
                        roles_json = _similar_json(connection, roles)
                    self._json({
                        "query": query,
                        "roles": roles_json,
                        "mapping_suggestions": _to_jsonable(suggestions),
                        "framework_scores": framework_scores,
                    })
                    return
                self.send_error(404)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/import-pd":
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._json({"error": "Invalid upload payload"}, 400)
                        return
                    filename = _safe_docx_filename(str(payload.get("filename") or ""))
                    encoded = str(payload.get("content_base64") or "")
                    if not encoded:
                        self._json({"error": "No file content supplied"}, 400)
                        return
                    document_path = _uploaded_pd_path(database_path, filename)
                    document_path.write_bytes(base64.b64decode(encoded))
                    extracted = extract_document(document_path)
                    with connect_database(database_path) as connection:
                        initialise_database(connection)
                        pd_id = import_document(connection, extracted)
                        seed_classification_references(connection)
                    record = extracted.get("pd_record", {})
                    self._json({
                        "ok": True,
                        "position_description_id": pd_id,
                        "role_title": record.get("role_title", ""),
                        "source_filename": record.get("source_filename", document_path.name),
                        "extraction_status": record.get("extraction_status", ""),
                        "validation_url": f"http://127.0.0.1:8765/?pd={pd_id}",
                    })
                    return
                if parsed.path == "/api/import-job-family-workbook":
                    payload = self._read_json()
                    if not isinstance(payload, dict):
                        self._json({"error": "Invalid upload payload"}, 400)
                        return
                    filename = _safe_workbook_filename(str(payload.get("filename") or ""))
                    encoded = str(payload.get("content_base64") or "")
                    if not encoded:
                        self._json({"error": "No file content supplied"}, 400)
                        return
                    workbook_path = _uploaded_job_family_path(database_path, filename)
                    workbook_path.write_bytes(base64.b64decode(encoded))
                    with connect_database(database_path) as connection:
                        initialise_database(connection)
                        summary = import_job_family_workbook(connection, workbook_path)
                        framework_embeddings = upsert_embeddings(
                            connection,
                            framework_embedding_sources(connection),
                            _embedder(model_name),
                            model_name=model_name,
                        )
                        status = job_family_import_status(connection)
                    self._json({
                        "ok": True,
                        "summary": {
                            "import_batch_id": summary.import_batch_id,
                            "framework_rows": summary.framework_rows,
                            "mapping_rows": summary.mapping_rows,
                            "mapping_rows_linked_to_pds": summary.mapping_rows_linked_to_pds,
                            "invalid_mapping_codes": summary.invalid_mapping_codes,
                            "framework_embeddings": framework_embeddings,
                        },
                        "status": status,
                    })
                    return
                if parsed.path.startswith("/api/pds/") and parsed.path.endswith("/prepare-intelligence"):
                    pd_id = int(parsed.path.split("/")[3])
                    with connect_database(database_path) as connection:
                        initialise_database(connection)
                        if pd_detail(connection, pd_id) is None:
                            self._json({"error": "Not found"}, 404)
                            return
                        summary = prepare_pd_intelligence(
                            connection,
                            pd_id,
                            _embedder(model_name),
                            model_name=model_name,
                        )
                    self._json({"ok": True, "summary": summary})
                    return
                if parsed.path.startswith("/api/pds/") and parsed.path.endswith("/assign-mappings"):
                    pd_id = int(parsed.path.split("/")[3])
                    payload = self._read_json()
                    codes = payload.get("mapping_codes", []) if isinstance(payload, dict) else []
                    if not isinstance(codes, list):
                        self._json({"error": "mapping_codes must be a list"}, 400)
                        return
                    rationale = str(payload.get("rationale") or "").strip() if isinstance(payload, dict) else ""
                    notes = (
                        f"Assigned in Mapping Assistant. Rationale: {rationale}"
                        if rationale
                        else "Assigned in Mapping Assistant"
                    )
                    with connect_database(database_path) as connection:
                        initialise_database(connection)
                        try:
                            mappings = assign_job_family_mappings(
                                connection,
                                pd_id,
                                codes,
                                validation_notes=notes,
                            )
                        except KeyError:
                            self._json({"error": "PD not found"}, 404)
                            return
                        except ValueError as exc:
                            self._json({"error": str(exc)}, 400)
                            return
                    self._json({"ok": True, "mappings": mappings})
                    return
                self.send_error(404)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def do_PUT(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/classifications":
                    payload = self._read_json()
                    rows = payload.get("rows", []) if isinstance(payload, dict) else []
                    with connect_database(database_path) as connection:
                        before = classification_rows(connection)
                        _classification_backup_path(database_path).write_text(
                            json.dumps(before, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        updated = update_classification_references(connection, rows)
                    self._json({"updated": updated})
                    return
                self.send_error(404)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def log_message(self, format: str, *args: object) -> None:
            pass
    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local PD role intelligence app")
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    connection = connect_database(args.database)
    try:
        initialise_database(connection)
        seed_classification_references(connection)
    finally:
        connection.close()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.database, args.model))
    print(f"PD role intelligence app: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
