from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from pd_extractor.classifications import classification_rows, update_classification_references
from pd_extractor.config import default_database_path
from pd_extractor.database import assign_job_family_mappings, connect_database, initialise_database
from pd_extractor.validation_app import confirm_validation, get_validation_record, save_validation_draft


ROOT = Path(__file__).resolve().parents[1]
GENERATED_TABLES = (
    "activity_statistics",
    "activity_rarity",
    "role_capability_profiles",
    "role_neighbours",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exercise backend writes on a disposable unified database copy"
    )
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "data" / "qa" / "unified_write_workflow_validation.json",
    )
    args = parser.parse_args()
    source = args.database.resolve()
    disposable = ROOT / "data" / "qa" / "pd_management_unified_write_test.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(disposable) + suffix)
        if candidate.exists():
            candidate.unlink()
    shutil.copy2(source, disposable)

    checks: dict[str, object] = {}
    connection = connect_database(disposable)
    try:
        initialise_database(connection)
        generated_before = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in GENERATED_TABLES
        }

        validation_id = connection.execute(
            "SELECT position_description_id FROM validation_records ORDER BY position_description_id LIMIT 1"
        ).fetchone()[0]
        record = get_validation_record(connection, validation_id)
        if record is None:
            raise RuntimeError("no validation record available")
        save_validation_draft(
            connection,
            validation_id,
            record["draft"],
            record["section_statuses"],
            record["edited_paths"],
        )
        errors = confirm_validation(
            connection,
            validation_id,
            record["draft"],
            record["section_statuses"],
            record["edited_paths"],
        )
        checks["validation_save_and_confirm"] = not errors

        mapping = connection.execute(
            "SELECT position_description_id, mapping_code FROM active_pd_job_family_mappings "
            "WHERE position_description_id IS NOT NULL AND mapping_code IS NOT NULL "
            "ORDER BY position_description_id, mapping_rank LIMIT 1"
        ).fetchone()
        assigned = assign_job_family_mappings(
            connection,
            int(mapping["position_description_id"]),
            [str(mapping["mapping_code"])],
            validation_notes="Disposable unified database workflow verification",
        )
        checks["mapping_assignment"] = len(assigned) == 1

        classifications = classification_rows(connection)
        checks["classification_update"] = (
            update_classification_references(connection, classifications) == len(classifications)
        )

        connection.execute("BEGIN")
        original_title = connection.execute(
            "SELECT role_title FROM position_descriptions WHERE id = ?", (validation_id,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE position_descriptions SET role_title = ? WHERE id = ?",
            (original_title + " [rollback test]", validation_id),
        )
        connection.rollback()
        checks["transaction_rollback"] = connection.execute(
            "SELECT role_title FROM position_descriptions WHERE id = ?", (validation_id,)
        ).fetchone()[0] == original_title

        checks["integrity_check"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
        checks["foreign_key_issues"] = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        generated_after = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in GENERATED_TABLES
        }
        checks["generated_tables_preserved"] = generated_after == generated_before
    finally:
        connection.close()

    status = "pass" if all(
        value is True or value == "ok" or value == 0 for value in checks.values()
    ) else "fail"
    result = {"status": status, "source_database": str(source), "checks": checks}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(disposable) + suffix)
        if candidate.exists():
            candidate.unlink()
    print(json.dumps(result, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
