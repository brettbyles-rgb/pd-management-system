from __future__ import annotations

import sqlite3
from pathlib import Path

from ..mapping_text import _is_boilerplate_accountability


def _clean(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        text = " ".join(str(item or "").split())
        while text[:1] in "-*•" or (len(text) > 2 and text[0].isdigit() and text[1] in ".)"):
            text = text.lstrip("-*• ").lstrip("0123456789").lstrip(".) ").strip()
        if len(text) > 12:
            out.append(text)
    return out


def _clean_one(item: str | None) -> str:
    cleaned = _clean([str(item or "")])
    return cleaned[0] if cleaned else ""


def load_from_pd_database(path: str | Path, limit: int | None = None) -> list[dict]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    sql = """
        SELECT
            pd.id AS position_description_id,
            pd.position_description_no,
            pd.role_title,
            pd.classification_grade_band,
            pd.division_branch_unit,
            section.section_text AS purpose,
            li.sequence,
            li.item_text
        FROM position_descriptions pd
        JOIN pd_list_items li
          ON li.position_description_id = pd.id
         AND li.section_name = 'key_accountabilities'
        LEFT JOIN pd_sections section
          ON section.position_description_id = pd.id
         AND LOWER(section.section_name) IN ('primary purpose', 'purpose')
        ORDER BY pd.id, li.sequence
    """
    by_id: dict[int, dict] = {}
    for row in connection.execute(sql):
        role = by_id.setdefault(
            int(row["position_description_id"]),
            {
                "pd_id": str(row["position_description_id"]),
                "position_description_id": int(row["position_description_id"]),
                "position_description_no": row["position_description_no"],
                "title": row["role_title"],
                "classification": row["classification_grade_band"],
                "job_family": None,
                "sub_family": row["division_branch_unit"],
                "purpose": row["purpose"],
                "accountabilities": [],
                "excluded_accountabilities": [],
                "source_accountability_count": 0,
            },
        )
        role["source_accountability_count"] += 1
        text = _clean_one(row["item_text"])
        if not text:
            continue
        reason = _is_boilerplate_accountability(text)
        if reason:
            role["excluded_accountabilities"].append(
                {
                    "sequence": row["sequence"],
                    "reason": reason,
                    "text": text,
                }
            )
        else:
            role["accountabilities"].append(text)
    connection.close()
    roles = []
    for role in by_id.values():
        if role["accountabilities"]:
            roles.append(role)
    return roles[:limit] if limit else roles
