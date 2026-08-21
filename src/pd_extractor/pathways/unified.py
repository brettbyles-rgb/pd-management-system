from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


UNIFIED_SCHEMA_VERSION = "1.0.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _drop_object(connection: sqlite3.Connection, name: str) -> None:
    row = connection.execute(
        "SELECT type FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    if not row:
        return
    object_type = "VIEW" if row[0] == "view" else "TABLE"
    connection.execute(f'DROP {object_type} "{name}"')


def _copy_pathway_table(
    connection: sqlite3.Connection, source: str, target: str | None = None
) -> None:
    target = target or source
    _drop_object(connection, target)
    connection.execute(f'CREATE TABLE "{target}" AS SELECT * FROM pathway."{source}"')


def _install_identity(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "position_descriptions")
    if "role_id" not in columns:
        connection.execute("ALTER TABLE position_descriptions ADD COLUMN role_id TEXT")
    if "record_status" not in columns:
        connection.execute(
            "ALTER TABLE position_descriptions ADD COLUMN record_status TEXT NOT NULL DEFAULT 'active'"
        )
    connection.execute(
        "UPDATE position_descriptions SET "
        "role_id = (SELECT role_id FROM pathway.roles "
        "WHERE CAST(pathway.roles.source_db_id AS INTEGER) = position_descriptions.id), "
        "record_status = COALESCE((SELECT record_status FROM pathway.roles "
        "WHERE CAST(pathway.roles.source_db_id AS INTEGER) = position_descriptions.id), 'active')"
    )
    missing = connection.execute(
        "SELECT COUNT(*) FROM position_descriptions WHERE role_id IS NULL OR role_id = ''"
    ).fetchone()[0]
    duplicates = connection.execute(
        "SELECT COUNT(*) FROM (SELECT role_id FROM position_descriptions "
        "GROUP BY role_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    if missing or duplicates:
        raise ValueError(
            f"stable role identity failed: missing={missing}, duplicate_groups={duplicates}"
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS position_descriptions_role_id_uq "
        "ON position_descriptions(role_id)"
    )


def _extend_operational_activity_data(connection: sqlite3.Connection) -> None:
    if "cluster_member_phrases" not in _columns(connection, "activity_definitions"):
        connection.execute(
            "ALTER TABLE activity_definitions ADD COLUMN cluster_member_phrases TEXT"
        )
    connection.execute(
        "UPDATE activity_definitions SET cluster_member_phrases = "
        "(SELECT cluster_member_phrases FROM pathway.activities "
        "WHERE pathway.activities.activity_id = activity_definitions.id)"
    )


def _install_pathway_tables(connection: sqlite3.Connection) -> None:
    for source, target in (
        ("capabilities", "pathway_capability_identities"),
        ("capability_level_rules", "capability_level_rules"),
        ("capability_applicability", "capability_applicability"),
        ("adjacency_rules", "adjacency_rules"),
        ("activity_rarity", "activity_rarity"),
        ("activity_statistics", "activity_statistics"),
        ("role_capability_profiles", "role_capability_profiles"),
        ("role_neighbours", "role_neighbours"),
        ("role_id_crosswalk", "role_id_crosswalk"),
        ("role_application_payloads", "role_application_payloads"),
        ("algorithm_parameters", "pathway_algorithm_parameters"),
        ("release_files", "pathway_release_files"),
        ("build_metadata", "pathway_build_metadata"),
    ):
        _copy_pathway_table(connection, source, target)

    connection.execute(
        "CREATE UNIQUE INDEX capability_applicability_role_uq "
        "ON capability_applicability(role_id)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX capability_level_rules_uq "
        "ON capability_level_rules(framework_name, raw_level)"
    )
    connection.execute(
        "CREATE INDEX activity_rarity_role_idx ON activity_rarity(role_id)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX activity_statistics_activity_uq "
        "ON activity_statistics(activity_id)"
    )
    connection.execute(
        "CREATE INDEX role_capability_profiles_role_idx "
        "ON role_capability_profiles(role_id)"
    )
    connection.execute(
        "CREATE INDEX role_neighbours_source_rank_idx "
        "ON role_neighbours(role_id, neighbour_rank)"
    )
    connection.execute(
        "CREATE INDEX role_neighbours_target_idx "
        "ON role_neighbours(neighbour_role_id)"
    )


def _install_compatibility_views(connection: sqlite3.Connection) -> None:
    view_names = (
        "roles",
        "classification_aliases",
        "job_family_nodes",
        "role_job_family_mappings",
        "pathway_capability_frameworks",
        "capabilities",
        "role_capabilities",
        "activities",
        "role_activities",
        "essential_requirements",
        "role_purposes",
        "key_accountabilities",
        "role_overview_audit",
        "role_activity_audit",
        "role_capability_audit",
        "role_neighbour_audit",
    )
    for name in view_names:
        _drop_object(connection, name)

    connection.execute(
        "CREATE VIEW roles AS SELECT "
        "role_id, CAST(id AS TEXT) AS source_db_id, source_filename, "
        "position_description_no AS pd_number, role_title AS title, "
        "classification_grade_band AS classification_raw, extraction_status, "
        "department_agency, division_branch_unit, anzsco_code, osca_code, pcat_code, "
        "date_of_approval, senior_executive_work_level_standards, record_status "
        "FROM position_descriptions"
    )
    connection.execute(
        "CREATE VIEW classification_aliases AS SELECT "
        "CAST(id AS TEXT) AS classification_id, raw_label, display_label, abbreviation, "
        "cohort, seniority_order, enterprise_agreement, active, notes, updated_at "
        "FROM classification_references"
    )
    connection.execute(
        "CREATE VIEW job_family_nodes AS SELECT "
        "e.code, e.name, e.level, e.parent_code, e.main_definition, "
        "e.supp_definition_1, e.supp_definition_2, e.exclusions, e.sequence "
        "FROM job_family_entries e JOIN job_family_import_batches b "
        "ON b.id = e.import_batch_id WHERE b.is_active = 1"
    )
    connection.execute(
        "CREATE VIEW role_job_family_mappings AS SELECT "
        "p.role_id, m.position_description_id, m.pd_id AS legacy_mapping_pd_id, "
        "m.mapping_rank, m.mapping_code, m.mapping_name, m.mapping_level, "
        "m.mapping_validated, m.validation_notes, m.framework_code_valid "
        "FROM pd_job_family_mappings m "
        "JOIN job_family_import_batches b ON b.id = m.import_batch_id AND b.is_active = 1 "
        "LEFT JOIN position_descriptions p ON p.id = m.position_description_id"
    )
    connection.execute(
        "CREATE VIEW pathway_capability_frameworks AS SELECT "
        "'framework:' || id AS framework_id, CAST(id AS TEXT) AS source_framework_id, "
        "framework_name FROM capability_frameworks"
    )
    connection.execute(
        "CREATE VIEW capabilities AS SELECT * FROM pathway_capability_identities"
    )
    connection.execute(
        "CREATE VIEW role_capabilities AS SELECT "
        "p.role_id, i.capability_id, CAST(pc.id AS TEXT) AS source_assignment_id, "
        "pc.position_description_id, pc.sequence, pc.capability_type, f.framework_name, "
        "d.capability_code, d.capability_name, pc.required_level, "
        "r.normalized_level, pc.capability_group, pc.description, pc.source_text "
        "FROM pd_capabilities pc "
        "JOIN position_descriptions p ON p.id = pc.position_description_id "
        "JOIN capability_definitions d ON d.id = pc.capability_definition_id "
        "JOIN capability_frameworks f ON f.id = d.framework_id "
        "JOIN pathway_capability_identities i "
        "ON CAST(i.source_capability_id AS INTEGER) = d.id "
        "LEFT JOIN capability_level_rules r "
        "ON r.framework_name = f.framework_name AND r.raw_level = pc.required_level"
    )
    connection.execute(
        "CREATE VIEW activities AS SELECT "
        "id AS activity_id, match_label AS canonical_match_label, "
        "plain_label AS canonical_plain_label, "
        "CASE discriminating WHEN 1 THEN 'Yes' ELSE 'No' END AS discriminating, "
        "CAST(cluster_id AS TEXT) AS cluster_id, CAST(raw_count AS TEXT) AS raw_count, "
        "cluster_member_phrases FROM activity_definitions"
    )
    connection.execute(
        "CREATE VIEW role_activities AS SELECT "
        "p.role_id, a.position_description_id, p.position_description_no AS pd_number, "
        "p.role_title AS title, a.activity_rank, a.activity_id, "
        "COALESCE((SELECT GROUP_CONCAT(gap_text, ' | ') FROM "
        "(SELECT gap_text FROM activity_assignment_gaps g "
        "WHERE g.position_description_id = a.position_description_id ORDER BY g.id)), '') "
        "AS assignment_gaps, '0' AS retry_count, 'No' AS fallback_used "
        "FROM position_description_activities a "
        "JOIN position_descriptions p ON p.id = a.position_description_id"
    )
    connection.execute(
        "CREATE VIEW essential_requirements AS SELECT "
        "p.role_id, i.position_description_id, i.sequence, "
        "'essential_requirement' AS requirement_type, i.item_text "
        "FROM pd_list_items i JOIN position_descriptions p "
        "ON p.id = i.position_description_id "
        "WHERE i.section_name = 'essential_requirements'"
    )
    connection.execute(
        "CREATE VIEW role_purposes AS SELECT p.role_id, s.section_text AS position_purpose "
        "FROM pd_sections s JOIN position_descriptions p ON p.id = s.position_description_id "
        "WHERE s.section_name = 'primary_purpose'"
    )
    connection.execute(
        "CREATE VIEW key_accountabilities AS SELECT "
        "p.role_id, i.sequence, i.item_text FROM pd_list_items i "
        "JOIN position_descriptions p ON p.id = i.position_description_id "
        "WHERE i.section_name = 'key_accountabilities'"
    )
    connection.execute(
        "CREATE VIEW role_overview_audit AS SELECT "
        "r.*, rp.position_purpose, ca.applicability_status AS capability_status, "
        "ca.reason AS capability_status_reason, "
        "(SELECT mapping_name FROM role_job_family_mappings m "
        "WHERE m.role_id = r.role_id AND CAST(m.mapping_rank AS INTEGER) = 1 LIMIT 1) "
        "AS primary_job_family_mapping "
        "FROM roles r LEFT JOIN role_purposes rp ON rp.role_id = r.role_id "
        "LEFT JOIN capability_applicability ca ON ca.role_id = r.role_id"
    )
    connection.execute(
        "CREATE VIEW role_activity_audit AS SELECT "
        "r.role_id, r.pd_number, r.title, ra.activity_rank, ra.activity_id, "
        "a.canonical_plain_label AS activity_name, s.roles_with_activity, "
        "s.total_active_roles, s.share, s.rarity_weight, ra.assignment_gaps "
        "FROM roles r JOIN role_activities ra ON ra.role_id = r.role_id "
        "LEFT JOIN activities a ON a.activity_id = ra.activity_id "
        "LEFT JOIN activity_statistics s ON s.activity_id = ra.activity_id"
    )
    connection.execute(
        "CREATE VIEW role_capability_audit AS SELECT "
        "r.role_id, r.pd_number, r.title, p.framework, p.capability_code, p.capability, "
        "p.raw_level, p.level AS normalized_level, p.focus, p.source_release, "
        "p.build_version, p.algorithm_version "
        "FROM roles r JOIN role_capability_profiles p ON p.role_id = r.role_id"
    )
    connection.execute(
        "CREATE VIEW role_neighbour_audit AS SELECT "
        "n.*, source.position_description_no AS source_pd_number, "
        "target.position_description_no AS neighbour_pd_number_business "
        "FROM role_neighbours n "
        "JOIN position_descriptions source ON source.role_id = n.role_id "
        "JOIN position_descriptions target ON target.role_id = n.neighbour_role_id"
    )


def _install_metadata(
    connection: sqlite3.Connection,
    pd_database: Path,
    pathway_database: Path,
    source_hashes: dict[str, str],
) -> None:
    for name in (
        "unified_build_metadata",
        "unified_source_databases",
        "unified_dataset_inventory",
    ):
        _drop_object(connection, name)
    built_at = datetime.now(timezone.utc).isoformat()
    pathway_metadata = dict(
        connection.execute("SELECT key, value FROM pathway_build_metadata")
    )
    connection.execute(
        "CREATE TABLE unified_build_metadata ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO unified_build_metadata(key, value) VALUES (?, ?)",
        [
            ("unified_schema_version", UNIFIED_SCHEMA_VERSION),
            ("built_at_utc", built_at),
            ("pathway_source_release", pathway_metadata["source_release"]),
            ("pathway_build_version", pathway_metadata["build_version"]),
            ("pathway_algorithm_version", pathway_metadata["algorithm_version"]),
            ("operational_authority", "PD Management System tables"),
            ("derived_authority", "versioned pathway build tables"),
        ],
    )
    connection.execute(
        "CREATE TABLE unified_source_databases ("
        "source_name TEXT PRIMARY KEY, source_path TEXT NOT NULL, sha256 TEXT NOT NULL, "
        "bytes INTEGER NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO unified_source_databases(source_name, source_path, sha256, bytes) "
        "VALUES (?, ?, ?, ?)",
        [
            (
                "pd_management_operational",
                str(pd_database),
                source_hashes["pd_management"],
                pd_database.stat().st_size,
            ),
            (
                "career_pathways_snapshot",
                str(pathway_database),
                source_hashes["career_pathways"],
                pathway_database.stat().st_size,
            ),
        ],
    )
    inventory = [
        ("position_descriptions", "table", "operational", 1171),
        ("roles", "view", "operational compatibility", 1171),
        ("role_capabilities", "view", "operational + calculated interpretation", 20891),
        ("role_activities", "view", "operational", 13936),
        ("role_job_family_mappings", "view", "active operational batch", 1310),
        ("essential_requirements", "view", "operational", 4689),
        ("activity_statistics", "table", "generated", 1256),
        ("activity_rarity", "table", "generated", 13936),
        ("role_capability_profiles", "table", "generated", 20891),
        ("role_neighbours", "table", "generated", 29275),
    ]
    connection.execute(
        "CREATE TABLE unified_dataset_inventory ("
        "dataset_name TEXT PRIMARY KEY, object_type TEXT NOT NULL, authority TEXT NOT NULL, "
        "expected_row_count INTEGER NOT NULL, actual_row_count INTEGER NOT NULL)"
    )
    rows = []
    for name, object_type, authority, expected in inventory:
        actual = connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        rows.append((name, object_type, authority, expected, actual))
    connection.executemany(
        "INSERT INTO unified_dataset_inventory VALUES (?, ?, ?, ?, ?)", rows
    )
    connection.execute("PRAGMA user_version = 1")


def _validate(connection: sqlite3.Connection) -> dict[str, Any]:
    expected = dict(
        connection.execute(
            "SELECT dataset_name, expected_row_count FROM unified_dataset_inventory"
        )
    )
    actual = {
        name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        for name in expected
    }
    count_mismatches = {
        name: {"expected": expected[name], "actual": actual[name]}
        for name in expected
        if expected[name] != actual[name]
    }
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_key_issues = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
    missing_role_ids = connection.execute(
        "SELECT COUNT(*) FROM position_descriptions WHERE role_id IS NULL OR role_id = ''"
    ).fetchone()[0]
    unresolved_neighbours = connection.execute(
        "SELECT COUNT(*) FROM role_neighbours n "
        "LEFT JOIN position_descriptions s ON s.role_id = n.role_id "
        "LEFT JOIN position_descriptions t ON t.role_id = n.neighbour_role_id "
        "WHERE s.id IS NULL OR t.id IS NULL"
    ).fetchone()[0]
    unreconciled_scores = connection.execute(
        "SELECT COUNT(*) FROM role_neighbours WHERE "
        "ABS(CAST(score AS REAL) - (CAST(readiness_contribution AS REAL) + "
        "CAST(activity_contribution AS REAL) + CAST(subfamily_contribution AS REAL) + "
        "CAST(classification_contribution AS REAL))) > 0.000002"
    ).fetchone()[0]

    def symmetric_difference(
        main_object: str, pathway_object: str, columns: tuple[str, ...]
    ) -> int:
        main_fields = ", ".join(
            f'COALESCE(CAST("{column}" AS TEXT), \'\')' for column in columns
        )
        pathway_fields = ", ".join(
            f'COALESCE(CAST("{column}" AS TEXT), \'\')' for column in columns
        )
        main_only = connection.execute(
            f'SELECT COUNT(*) FROM (SELECT {main_fields} FROM main."{main_object}" '
            f'EXCEPT SELECT {pathway_fields} FROM pathway."{pathway_object}")'
        ).fetchone()[0]
        pathway_only = connection.execute(
            f'SELECT COUNT(*) FROM (SELECT {pathway_fields} FROM pathway."{pathway_object}" '
            f'EXCEPT SELECT {main_fields} FROM main."{main_object}")'
        ).fetchone()[0]
        return main_only + pathway_only

    projection_columns = {
        "roles": (
            "role_id",
            "source_db_id",
            "source_filename",
            "pd_number",
            "title",
            "classification_raw",
            "extraction_status",
            "department_agency",
            "division_branch_unit",
            "anzsco_code",
            "osca_code",
            "pcat_code",
            "date_of_approval",
            "senior_executive_work_level_standards",
            "record_status",
        ),
        "classification_aliases": (
            "classification_id",
            "raw_label",
            "display_label",
            "abbreviation",
            "cohort",
            "seniority_order",
            "enterprise_agreement",
            "active",
            "notes",
            "updated_at",
        ),
        "job_family_nodes": (
            "code",
            "name",
            "level",
            "parent_code",
            "main_definition",
            "supp_definition_1",
            "supp_definition_2",
            "exclusions",
            "sequence",
        ),
        "role_job_family_mappings": (
            "role_id",
            "position_description_id",
            "legacy_mapping_pd_id",
            "mapping_rank",
            "mapping_code",
            "mapping_name",
            "mapping_level",
            "mapping_validated",
            "validation_notes",
            "framework_code_valid",
        ),
        "role_capabilities": (
            "role_id",
            "capability_id",
            "source_assignment_id",
            "position_description_id",
            "sequence",
            "capability_type",
            "framework_name",
            "capability_code",
            "capability_name",
            "required_level",
            "normalized_level",
            "capability_group",
            "description",
            "source_text",
        ),
        "essential_requirements": (
            "role_id",
            "position_description_id",
            "sequence",
            "requirement_type",
            "item_text",
        ),
    }
    projection_mismatches = {
        name: symmetric_difference(name, name, columns)
        for name, columns in projection_columns.items()
    }
    projection_mismatches["role_activities_core"] = symmetric_difference(
        "role_activities",
        "role_activities",
        (
            "role_id",
            "position_description_id",
            "pd_number",
            "title",
            "activity_rank",
            "activity_id",
        ),
    )
    activity_fields = (
        "activity_id",
        "canonical_match_label",
        "canonical_plain_label",
        "discriminating",
        "cluster_id",
        "raw_count",
        "cluster_member_phrases",
    )
    activity_select = ", ".join(
        f'COALESCE(CAST("{column}" AS TEXT), \'\')' for column in activity_fields
    )
    projection_mismatches["pathway_activities_missing_from_operational"] = (
        connection.execute(
            f'SELECT COUNT(*) FROM (SELECT {activity_select} FROM pathway.activities '
            f'EXCEPT SELECT {activity_select} FROM main.activities)'
        ).fetchone()[0]
    )
    projection_mismatches = {
        name: count for name, count in projection_mismatches.items() if count
    }
    status = "pass" if not any(
        (
            integrity != "ok",
            foreign_key_issues,
            missing_role_ids,
            unresolved_neighbours,
            unreconciled_scores,
            count_mismatches,
            projection_mismatches,
        )
    ) else "fail"
    return {
        "status": status,
        "integrity_check": integrity,
        "foreign_key_issues": foreign_key_issues,
        "missing_role_ids": missing_role_ids,
        "unresolved_neighbours": unresolved_neighbours,
        "unreconciled_scores": unreconciled_scores,
        "count_mismatches": count_mismatches,
        "pathway_projection_mismatches": projection_mismatches,
        "dataset_counts": actual,
    }


def build_unified_database(
    pd_database: Path,
    pathway_database: Path,
    output: Path,
    report: Path,
) -> dict[str, Any]:
    pd_database = pd_database.resolve()
    pathway_database = pathway_database.resolve()
    output = output.resolve()
    report = report.resolve()
    if not pd_database.exists() or not pathway_database.exists():
        raise FileNotFoundError("both source databases are required")
    source_hashes = {
        "pd_management": _sha256(pd_database),
        "career_pathways": _sha256(pathway_database),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.sqlite3")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(pd_database, temporary)
    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("ATTACH DATABASE ? AS pathway", (str(pathway_database),))
        connection.execute("BEGIN IMMEDIATE")
        _install_identity(connection)
        _extend_operational_activity_data(connection)
        _install_pathway_tables(connection)
        _install_compatibility_views(connection)
        _install_metadata(
            connection, pd_database, pathway_database, source_hashes
        )
        connection.commit()
        validation = _validate(connection)
        connection.execute("DETACH DATABASE pathway")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    if validation["status"] != "pass":
        raise ValueError(f"unified database validation failed: {validation}")
    if output.exists():
        output.unlink()
    temporary.replace(output)
    result = {
        "unified_database": str(output),
        "bytes": output.stat().st_size,
        "sha256": _sha256(output),
        "schema_version": UNIFIED_SCHEMA_VERSION,
        "source_databases": source_hashes,
        "validation": validation,
    }
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the unified PD Management and Career Pathways database"
    )
    parser.add_argument(
        "--pd-database",
        type=Path,
        default=Path("output/pd-management-bulk-fixed.sqlite3"),
    )
    parser.add_argument(
        "--pathway-database",
        type=Path,
        default=Path("data/generated/career_pathways.sqlite3"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/generated/pd_management_unified.sqlite3"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/qa/unified_database_validation.json"),
    )
    args = parser.parse_args(argv)
    result = build_unified_database(
        args.pd_database, args.pathway_database, args.output, args.report
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
