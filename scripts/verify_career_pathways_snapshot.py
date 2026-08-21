from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the auditable Career Pathways snapshot")
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path("data/generated/career_pathways.sqlite3"),
    )
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    try:
        objects = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
            )
        }
        required = {
            "activity_rarity",
            "activity_statistics",
            "role_capability_profiles",
            "role_neighbours",
            "algorithm_parameters",
            "release_files",
            "role_application_payloads",
            "role_activity_audit",
            "role_capability_audit",
            "role_neighbour_audit",
        }
        missing = sorted(required - objects.keys())
        counts = dict(connection.execute("SELECT dataset_name, row_count FROM dataset_inventory"))
        unreconciled_scores = connection.execute(
            "SELECT COUNT(*) FROM role_neighbours WHERE "
            "ABS(CAST(score AS REAL) - (CAST(readiness_contribution AS REAL) + "
            "CAST(activity_contribution AS REAL) + CAST(subfamily_contribution AS REAL) + "
            "CAST(classification_contribution AS REAL))) > 0.000002"
        ).fetchone()[0]
        metadata = dict(connection.execute("SELECT key, value FROM build_metadata"))
        result = {
            "database": str(args.database.resolve()),
            "status": "pass" if not missing and not unreconciled_scores else "fail",
            "metadata": metadata,
            "missing_required_objects": missing,
            "unreconciled_scores": unreconciled_scores,
            "dataset_counts": counts,
        }
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "pass" else 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
