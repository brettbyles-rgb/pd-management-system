from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "postgresql"


def _database_url(environment_variable: str) -> str:
    value = os.environ.get(environment_variable, "").strip()
    if not value:
        raise SystemExit(f"Set {environment_variable} in the current process before migrating")
    if not value.lower().startswith(("postgresql://", "postgres://")):
        raise SystemExit(f"{environment_variable} is not a PostgreSQL URL")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply versioned PostgreSQL schema migrations")
    parser.add_argument(
        "--database-url-env",
        default="PD_MANAGEMENT_DATABASE_URL",
        help="Name of the environment variable containing the protected connection URL",
    )
    args = parser.parse_args()
    database_url = _database_url(args.database_url_env)

    import psycopg

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit("No PostgreSQL migrations found")

    with psycopg.connect(database_url, sslmode="require", connect_timeout=10) as connection:
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
