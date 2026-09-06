from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from postgres_connection import add_connection_arguments, connection_arguments


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "postgresql"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply versioned PostgreSQL schema migrations")
    add_connection_arguments(parser)
    args = parser.parse_args()
    positional, keywords = connection_arguments(args)

    import psycopg

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit("No PostgreSQL migrations found")

    with psycopg.connect(*positional, **keywords) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   sha256 TEXT NOT NULL,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('pd_management_schema_migrations'))")
        applied = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT version, sha256 FROM schema_migrations"
            ).fetchall()
        }
        for migration in files:
            version = migration.name
            sql = migration.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if version in applied:
                if applied[version] != digest:
                    raise SystemExit(f"Applied migration was modified: {version}")
                print(f"already applied: {version}")
                continue
            connection.execute(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, sha256) VALUES (%s, %s)",
                (version, digest),
            )
            print(f"applied: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
