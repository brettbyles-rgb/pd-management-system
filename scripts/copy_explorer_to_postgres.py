from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from postgres_connection import add_connection_arguments, open_postgres_connection


EXPLORER_TABLES = (
    "position_descriptions",
    "classification_references",
    "job_family_import_batches",
    "job_family_entries",
    "pd_job_family_mappings",
    "activity_definitions",
    "activity_statistics",
    "position_description_activities",
    "activity_assignment_gaps",
    "capability_frameworks",
    "capability_definitions",
    "pd_capabilities",
    "pathway_capability_identities",
    "capability_level_rules",
    "role_neighbours",
    "constellation_algorithm_versions",
    "constellation_candidate_scores",
)

ADMIN_TABLES = (
    "role_description_fields",
    "pd_sections",
    "pd_list_items",
    "key_relationships",
    "capability_indicators",
    "extraction_issues",
    "validation_records",
    "validation_events",
    "pd_assigned_job_family_mappings",
    "pd_mapping_texts",
    "embeddings",
)

TABLE_SCOPES = {
    "explorer": EXPLORER_TABLES,
    "admin": ADMIN_TABLES,
    "all": EXPLORER_TABLES + ADMIN_TABLES,
}


def _source_counts(source: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, int]:
    return {
        table: int(source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in tables
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy the approved read-only Explorer snapshot from SQLite to PostgreSQL"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--scope",
        choices=tuple(TABLE_SCOPES),
        default="explorer",
        help="Table group to inspect or copy (default: explorer)",
    )
    parser.add_argument("--apply", action="store_true", help="Perform the copy; otherwise only inspect")
    add_connection_arguments(parser)
    args = parser.parse_args()

    source_path = args.source.resolve()
    if not source_path.is_file():
        raise SystemExit(f"SQLite source does not exist: {source_path}")
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    tables = TABLE_SCOPES[args.scope]
    counts = _source_counts(source, tables)
    print(f"source: {source_path}")
    for table, count in counts.items():
        print(f"{table}: {count}")
    if not args.apply:
        print("inspection only; use --apply after reviewing these counts")
        return 0

    import psycopg
    from psycopg import sql

    with open_postgres_connection(psycopg, args) as target:
        for table in tables:
            existing = target.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()[0]
            if existing:
                raise SystemExit(
                    f"Target table {table} is not empty; copy stopped without replacing data"
                )

        with target.cursor() as writer:
            for table in tables:
                columns = [
                    str(row[1])
                    for row in source.execute(f'PRAGMA table_info("{table}")').fetchall()
                ]
                statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                )
                cursor = source.execute(f'SELECT * FROM "{table}"')
                while batch := cursor.fetchmany(1000):
                    writer.executemany(
                        statement,
                        [tuple(row[column] for column in columns) for row in batch],
                    )
                print(f"copied: {table} ({counts[table]})")

        for table, expected in counts.items():
            actual = target.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()[0]
            if actual != expected:
                raise RuntimeError(f"Count mismatch for {table}: {actual} != {expected}")
    print("copy and table-count reconciliation complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
