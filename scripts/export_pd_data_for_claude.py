from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


def _none_if_empty(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    return value


def _rows_by_pd(
    connection: sqlite3.Connection,
    query: str,
) -> dict[int, list[sqlite3.Row]]:
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in connection.execute(query):
        if row["position_description_id"] is None:
            continue
        grouped[int(row["position_description_id"])].append(row)
    return grouped


def _framework_entries(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        str(row["code"]): row
        for row in connection.execute(
            """SELECT code, name, level, parent_code
               FROM active_job_family_entries"""
        )
        if row["code"] is not None
    }


def _hierarchy_for_code(
    entries: dict[str, sqlite3.Row],
    code: str | None,
) -> list[sqlite3.Row]:
    hierarchy: list[sqlite3.Row] = []
    seen: set[str] = set()
    current = entries.get(str(code)) if code is not None else None
    while current is not None:
        current_code = str(current["code"])
        if current_code in seen:
            break
        seen.add(current_code)
        hierarchy.append(current)
        parent_code = current["parent_code"]
        current = entries.get(str(parent_code)) if parent_code is not None else None
    return list(reversed(hierarchy))


def _level_name(hierarchy: list[sqlite3.Row], expected: str) -> str | None:
    expected_lower = expected.lower()
    for item in hierarchy:
        if expected_lower in str(item["level"] or "").lower():
            return _none_if_empty(item["name"])
    return None


def _capability(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "type": _none_if_empty(row["capability_type"]),
        "framework": _none_if_empty(row["framework"]),
        "group": _none_if_empty(row["capability_group"]),
        "capability": _none_if_empty(row["capability_name"]),
        "code": _none_if_empty(row["capability_code"]),
        "level": _none_if_empty(row["required_level"]),
        "description": _none_if_empty(row["description"]),
        "source_text": _none_if_empty(row["source_text"]),
    }


def _classification_references(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(row["raw_label"]): {
            "raw_label": _none_if_empty(row["raw_label"]),
            "display_label": _none_if_empty(row["display_label"]),
            "abbreviation": _none_if_empty(row["abbreviation"]),
            "cohort": _none_if_empty(row["cohort"]),
            "seniority_order": row["seniority_order"],
            "enterprise_agreement": _none_if_empty(row["enterprise_agreement"]),
            "active": row["active"],
            "notes": _none_if_empty(row["notes"]),
            "updated_at": _none_if_empty(row["updated_at"]),
        }
        for row in connection.execute(
            """SELECT raw_label, display_label, abbreviation, cohort,
                      seniority_order, enterprise_agreement, active, notes, updated_at
               FROM classification_references"""
        )
        if row["raw_label"] is not None
    }


def export_pd_data(database_path: Path, output_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        roles = connection.execute(
            """SELECT id, position_description_no, role_title,
                      classification_grade_band
               FROM position_descriptions
               ORDER BY position_description_no, role_title, id"""
        ).fetchall()

        sections_by_pd = _rows_by_pd(
            connection,
            """SELECT position_description_id, section_name, section_text
               FROM pd_sections
               ORDER BY position_description_id, section_name""",
        )
        list_items_by_pd = _rows_by_pd(
            connection,
            """SELECT position_description_id, section_name, sequence, item_text
               FROM pd_list_items
               ORDER BY position_description_id, section_name, sequence, id""",
        )
        capabilities_by_pd = _rows_by_pd(
            connection,
            """SELECT position_description_id, sequence, capability_type, framework,
                      capability_name, capability_code, required_level,
                      capability_group, description, source_text
               FROM pd_capabilities_readable
               ORDER BY position_description_id, sequence, pd_capability_id""",
        )
        mappings_by_pd = _rows_by_pd(
            connection,
            """SELECT position_description_id, pd_id, position_title, position_grade,
                      mapping_rank, mapping_code, mapping_name, mapping_level,
                      mapping_validated, validation_notes, framework_code_valid
               FROM active_pd_job_family_mappings
               ORDER BY position_description_id, mapping_rank, id""",
        )
        entries = _framework_entries(connection)
        classification_references = _classification_references(connection)

        output: list[dict[str, Any]] = []
        focus_count = 0
        key_accountability_count = 0
        distinct_levels: set[Any] = set()
        roles_with_classification_order = 0

        for role in roles:
            pd_key = int(role["id"])
            raw_classification = _none_if_empty(role["classification_grade_band"])
            classification_reference = classification_references.get(
                str(raw_classification)
            ) if raw_classification is not None else None
            if classification_reference is not None and classification_reference["seniority_order"] is not None:
                roles_with_classification_order += 1
            sections = {
                row["section_name"]: row["section_text"]
                for row in sections_by_pd.get(pd_key, [])
            }
            key_accountabilities = [
                _none_if_empty(row["item_text"])
                for row in list_items_by_pd.get(pd_key, [])
                if row["section_name"] == "key_accountabilities"
            ]
            if key_accountabilities:
                key_accountability_count += 1

            all_capabilities = [
                _capability(row)
                for row in capabilities_by_pd.get(pd_key, [])
            ]
            for capability in all_capabilities:
                distinct_levels.add(capability["level"])
            focus_capabilities = [
                capability
                for capability in all_capabilities
                if str(capability["type"] or "").lower() == "focus"
            ]
            if focus_capabilities:
                focus_count += 1

            mappings = []
            for mapping in mappings_by_pd.get(pd_key, []):
                hierarchy = _hierarchy_for_code(entries, mapping["mapping_code"])
                mappings.append({
                    "rank": mapping["mapping_rank"],
                    "code": _none_if_empty(mapping["mapping_code"]),
                    "name": _none_if_empty(mapping["mapping_name"]),
                    "level": _none_if_empty(mapping["mapping_level"]),
                    "validated": _none_if_empty(mapping["mapping_validated"]),
                    "validation_notes": _none_if_empty(mapping["validation_notes"]),
                    "framework_code_valid": mapping["framework_code_valid"],
                    "job_family": _level_name(hierarchy, "job family"),
                    "sub_family": _level_name(hierarchy, "sub"),
                    "specialisation": _level_name(hierarchy, "special"),
                })

            primary = mappings[0] if mappings else {}
            output.append({
                "pd_id": _none_if_empty(role["position_description_no"]),
                "title": _none_if_empty(role["role_title"]),
                "classification": raw_classification,
                "classification_reference": classification_reference,
                "job_family": primary.get("job_family"),
                "sub_family": primary.get("sub_family"),
                "specialisation": primary.get("specialisation"),
                "job_family_mappings": mappings,
                "position_purpose": _none_if_empty(sections.get("primary_purpose")),
                "key_accountabilities": key_accountabilities,
                "focus_capabilities": focus_capabilities,
                "all_capabilities": all_capabilities,
            })

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "output_path": str(output_path),
            "total_roles": len(output),
            "roles_with_focus_capabilities": focus_count,
            "roles_with_key_accountabilities": key_accountability_count,
            "roles_with_classification_order": roles_with_classification_order,
            "distinct_capability_levels": sorted(
                distinct_levels,
                key=lambda value: "" if value is None else str(value),
            ),
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("output/pd-management-bulk-fixed.sqlite3"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/pd-data-for-claude-career-pathways.json"),
    )
    args = parser.parse_args()
    summary = export_pd_data(args.database, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
