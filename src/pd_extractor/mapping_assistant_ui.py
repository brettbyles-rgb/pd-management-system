from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


GUIDE_MIN_SCORE = 0.30
TEMPLATE_PATH = Path(__file__).with_name("templates") / "mapping_assistant.html"


def _is_level(value: object, expected: str) -> bool:
    return expected.lower() in str(value or "").strip().lower()


def _validated(value: object) -> bool:
    return str(value or "").strip().lower() in {"yes", "validated", "true", "y"}


def _evidence_score(similarities: list[float], validated: int, evidence: int) -> float:
    ordered = sorted(similarities, reverse=True)
    if not ordered:
        return 0.0
    best = ordered[0]
    avg_top_3 = sum(ordered[:3]) / min(3, len(ordered))
    validation_signal = validated / evidence if evidence else 0.0
    evidence_signal = max(0, min(evidence, 3) - 1) / 2
    return 0.25 * best + 0.60 * avg_top_3 + 0.03 * validation_signal + 0.12 * evidence_signal


def _longest_prefix_parent(
    entry: dict[str, Any],
    entries: dict[str, dict[str, Any]],
    parent_level: str,
) -> str:
    code = str(entry.get("code") or "")
    candidates = [
        candidate
        for candidate in entries.values()
        if _is_level(candidate.get("level"), parent_level)
        and str(candidate.get("code") or "") != code
    ]
    candidates.sort(
        key=lambda candidate: (
            len(
                next(
                    (
                        prefix
                        for prefix in (
                            str(candidate.get("code") or "")[:index]
                            for index in range(len(str(candidate.get("code") or "")), -1, -1)
                        )
                        if code.startswith(prefix)
                    ),
                    "",
                )
            ),
            str(candidate.get("code") or ""),
        ),
        reverse=True,
    )
    return str(candidates[0].get("code") or "") if candidates else ""


def _normalise_parent_codes(entries: dict[str, dict[str, Any]]) -> None:
    for entry in entries.values():
        level = str(entry.get("level") or "")
        parent_code = str(entry.get("parent_code") or "")
        parent = entries.get(parent_code)
        expected = "Sub-family" if _is_level(level, "special") else "Job Family" if _is_level(level, "sub") else ""
        if not expected:
            entry["parent_code"] = ""
            continue
        if parent and _is_level(parent.get("level"), expected):
            continue
        entry["parent_code"] = _longest_prefix_parent(entry, entries, expected)


def _mapping_hierarchy_for_code(
    code: str,
    entries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = entries.get(code)
    while current and current["code"] not in seen:
        seen.add(current["code"])
        lineage.append(current)
        current = entries.get(str(current.get("parent_code") or ""))
    return list(reversed(lineage))


def _framework_nodes(
    similar_roles: list[dict[str, Any]],
    framework_scores: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    entries = {
        str(code): {
            **dict(value),
            "code": str(value.get("code") or code),
            "name": str(value.get("name") or ""),
            "level": str(value.get("level") or ""),
            "parent_code": str(value.get("parent_code") or ""),
        }
        for code, value in framework_scores.items()
    }
    _normalise_parent_codes(entries)

    similarities: dict[str, list[float]] = defaultdict(list)
    validated_counts: dict[str, int] = defaultdict(int)
    evidence_counts: dict[str, int] = defaultdict(int)
    for role in similar_roles:
        hierarchy = role.get("mapping_hierarchy") or []
        is_validated = _validated(role.get("mapping_validated"))
        similarity = float(role.get("similarity") or 0)
        for item in hierarchy:
            code = str(item.get("code") or "")
            if not code:
                continue
            similarities[code].append(similarity)
            evidence_counts[code] += 1
            validated_counts[code] += int(is_validated)

    for code, entry in entries.items():
        evidence_score = _evidence_score(
            similarities[code],
            validated_counts[code],
            evidence_counts[code],
        )
        framework_similarity = float(entry.get("framework_similarity") or 0)
        entry["score"] = 0.80 * evidence_score + 0.20 * framework_similarity
        entry["val"] = validated_counts[code]
        entry["thr"] = entry["score"] >= GUIDE_MIN_SCORE

    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries.values():
        children[str(entry.get("parent_code") or "")].append(entry)
    for rows in children.values():
        rows.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("name") or "")))

    families = [
        entry for entry in entries.values()
        if _is_level(entry.get("level"), "job family")
    ]
    families.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("name") or "")))
    families = families[:4]

    output = []
    for family in families:
        subs = []
        for sub in [
            row for row in children.get(family["code"], [])
            if _is_level(row.get("level"), "sub")
        ]:
            specs = [
                {
                    "id": spec["code"],
                    "name": spec["name"],
                    "score": spec["score"],
                    "val": spec["val"],
                    "thr": spec["thr"],
                    "main": str(spec.get("main_definition") or ""),
                    "supp": str(spec.get("supp_definition_1") or spec.get("supp_definition_2") or ""),
                    "excl": str(spec.get("exclusions") or ""),
                }
                for spec in children.get(sub["code"], [])
                if _is_level(spec.get("level"), "special")
            ]
            subs.append({
                "id": sub["code"],
                "name": sub["name"],
                "score": sub["score"],
                "val": sub["val"],
                "thr": sub["thr"],
                "specsTotal": len(specs),
                "main": str(sub.get("main_definition") or ""),
                "supp": str(sub.get("supp_definition_1") or sub.get("supp_definition_2") or ""),
                "excl": str(sub.get("exclusions") or ""),
                "specs": specs,
            })
        output.append({
            "id": family["code"],
            "name": family["name"],
            "score": family["score"],
            "val": family["val"],
            "subsTotal": len(subs),
            "main": str(family.get("main_definition") or ""),
            "supp": str(family.get("supp_definition_1") or family.get("supp_definition_2") or ""),
            "excl": str(family.get("exclusions") or ""),
            "subs": subs,
        })
    return output, entries


def _roster_payload(
    connection: sqlite3.Connection,
    framework_codes: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not framework_codes:
        return {}, {}
    placeholders = ",".join("?" for _ in framework_codes)
    rows = connection.execute(
        f"""SELECT m.mapping_code, pd.id AS position_description_id,
                   pd.position_description_no, pd.role_title,
                   COALESCE(NULLIF(cr.abbreviation, ''), pd.classification_grade_band, '') AS grade
            FROM active_pd_job_family_mappings m
            JOIN position_descriptions pd ON pd.id = m.position_description_id
            LEFT JOIN classification_references cr
                 ON cr.raw_label = pd.classification_grade_band
            WHERE m.mapping_code IN ({placeholders})
            ORDER BY m.mapping_code, pd.role_title, pd.position_description_no""",
        framework_codes,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pd_ids: set[int] = set()
    for row in rows:
        grouped[str(row["mapping_code"])].append({
            "role": row["role_title"] or "",
            "pd": row["position_description_no"] or "",
            "grade": row["grade"] or "",
        })
        pd_ids.add(int(row["position_description_id"]))

    roster = {
        code: {"total": len(items), "roles": items}
        for code, items in grouped.items()
    }
    if not pd_ids:
        return roster, {}

    pd_placeholders = ",".join("?" for _ in pd_ids)
    purposes = {
        int(row["position_description_id"]): row["section_text"]
        for row in connection.execute(
            f"""SELECT position_description_id, section_text
                FROM pd_sections
                WHERE position_description_id IN ({pd_placeholders})
                  AND LOWER(section_name) IN ('primary_purpose', 'primary purpose')""",
            list(pd_ids),
        )
    }
    accountabilities: dict[int, list[str]] = defaultdict(list)
    totals: dict[int, int] = defaultdict(int)
    for row in connection.execute(
        f"""SELECT position_description_id, sequence, item_text
            FROM pd_list_items
            WHERE position_description_id IN ({pd_placeholders})
              AND section_name = 'key_accountabilities'
            ORDER BY position_description_id, sequence""",
        list(pd_ids),
    ):
        pd_id = int(row["position_description_id"])
        totals[pd_id] += 1
        if len(accountabilities[pd_id]) < 3:
            accountabilities[pd_id].append(row["item_text"])

    detail_by_number = {
        row["position_description_no"] or "": {
            "purpose": purposes.get(int(row["id"]), ""),
            "acc": accountabilities.get(int(row["id"]), []),
            "accTotal": totals.get(int(row["id"]), 0),
        }
        for row in connection.execute(
            f"""SELECT id, position_description_no
                FROM position_descriptions
                WHERE id IN ({pd_placeholders})""",
            list(pd_ids),
        )
    }
    return roster, detail_by_number


def build_mapping_assistant_payload(
    connection: sqlite3.Connection,
    detail: dict[str, Any],
    assigned_mappings: list[dict[str, Any]],
    similar_roles: list[dict[str, Any]],
    framework_scores: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    families, entries = _framework_nodes(similar_roles, framework_scores)
    family_codes = {
        code
        for family in families
        for code in (
            [family["id"]]
            + [sub["id"] for sub in family["subs"]]
            + [spec["id"] for sub in family["subs"] for spec in sub["specs"]]
        )
    }
    roster, pd_detail = _roster_payload(connection, sorted(family_codes))
    current = " → ".join(
        item["name"]
        for item in _mapping_hierarchy_for_code(
            str(assigned_mappings[0]["mapping_code"]),
            entries,
        )
    ) if assigned_mappings else "Unmapped"
    classification = (
        detail.get("classification_abbreviation")
        or detail.get("classification_display")
        or detail.get("classification_grade_band")
        or ""
    )
    cohort = detail.get("classification_cohort") or ""
    executive = "executive" in str(cohort).lower() or "psse" in str(classification).lower()
    return {
        "PD": {
            "databaseId": int(detail["id"]),
            "id": detail.get("position_description_no") or "",
            "title": detail.get("role_title") or "",
            "classification": classification,
            "cohort": cohort,
            "current": current,
            "assigned": None,
            "executive": executive,
        },
        "FAMILIES": families,
        "ROSTER": roster,
        "PDDETAIL": pd_detail,
    }


def render_mapping_assistant(payload: dict[str, Any], *, read_only: bool = False) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    data_hook = f"<script>window.__MAPPING_DATA__={payload_json};</script>\n<script>\n/* ============ Data"
    template = template.replace("<script>\n/* ============ Data", data_hook, 1)
    live_data_hook = """Object.assign(PD,window.__MAPPING_DATA__.PD);
FAMILIES.splice(0,FAMILIES.length,...window.__MAPPING_DATA__.FAMILIES);
Object.keys(PDDETAIL).forEach(key=>delete PDDETAIL[key]);
Object.assign(PDDETAIL,window.__MAPPING_DATA__.PDDETAIL);
Object.keys(ROSTER).forEach(key=>delete ROSTER[key]);
Object.assign(ROSTER,window.__MAPPING_DATA__.ROSTER);

const state={"""
    template = template.replace("const state={", live_data_hook, 1)
    template = template.replace(
        "const state={openFam:'bs'",
        "const state={openFam:FAMILIES[0]?.id||null",
        1,
    )
    template = template.replace(
        "document.addEventListener('click',e=>{\n  const el=e.target.closest('[data-act]');",
        "document.addEventListener('click',async e=>{\n  const el=e.target.closest('[data-act]');",
        1,
    )
    old_assign = """case 'assign':{const inc=state.shortlist.filter(x=>state.include.has(x.ids.join('>')));const prim=state.shortlist.find(x=>x.ids.join('>')===state.primary);
      PD.assigned=prim.names.join(' → ')+(inc.length>1?` (+${inc.length-1} more)`:'' );
      toast(`${inc.length} mapping${inc.length>1?'s':''} assigned — sent to validation queue`);
      state.view='browse';state.shortlist=[];state.include=new Set();state.primary=null;
      state.rollupDismissed=new Set();state.rationale='';state.rosterOpen=new Set();render();break;}"""
    # The reference has no space before the closing parenthesis in the first line.
    old_assign = old_assign.replace("`:'' );", "`:'');")
    new_assign = """case 'assign':{const inc=state.shortlist.filter(x=>state.include.has(x.ids.join('>')));const prim=state.shortlist.find(x=>x.ids.join('>')===state.primary);
      const ordered=[prim,...inc.filter(x=>x!==prim)];
      if(ordered.length>3){toast('Select no more than three mappings.');break;}
      const btn=$('#assignBtn');if(btn)btn.disabled=true;
      try{
        const response=await fetch(`/api/pds/${PD.databaseId}/assign-mappings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mapping_codes:ordered.map(x=>x.node.id),rationale:state.rationale})});
        const result=await response.json();
        if(!response.ok)throw new Error(result.error||'Assignment failed');
        PD.assigned=prim.names.join(' → ')+(inc.length>1?` (+${inc.length-1} more)`:'');
        toast(`${inc.length} mapping${inc.length>1?'s':''} assigned — sent to validation queue`);
        state.view='browse';state.shortlist=[];state.include=new Set();state.primary=null;
        state.rollupDismissed=new Set();state.rationale='';state.rosterOpen=new Set();render();
      }catch(error){toast(error.message||'Assignment failed');if(btn)btn.disabled=false;}
      break;}"""
    if old_assign not in template:
        raise ValueError("Could not locate the reference assignment action")
    template = template.replace(old_assign, new_assign, 1)
    if not read_only:
        return template

    template = template.replace(
        "</style>",
        ".readonly-banner{background:#fff4d8;border-bottom:1px solid #e6c878;color:#684b00;"
        "padding:10px 24px;text-align:center;font-weight:800}"
        "</style>",
        1,
    )
    template = template.replace(
        "<body>",
        '<body><div class="readonly-banner">Hosted read-only proof of concept — '
        "mapping evidence is available, but assignments are disabled.</div>",
        1,
    )
    template = template.replace(
        "function updateAssignBar(){\n  const btn=$('#assignBtn');const s=$('#assignSumm');if(!btn||!s)return;",
        "function updateAssignBar(){\n  const btn=$('#assignBtn');const s=$('#assignSumm');if(!btn||!s)return;"
        "btn.disabled=true;btn.textContent='Assignment disabled';"
        "s.textContent='Hosted read-only proof of concept';return;",
        1,
    )
    return template
