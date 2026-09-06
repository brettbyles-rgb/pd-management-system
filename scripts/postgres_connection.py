from __future__ import annotations

import argparse
import getpass
import os
from typing import Any


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database-url-env", default="PD_MANAGEMENT_DATABASE_URL")
    parser.add_argument("--host", help="PostgreSQL host (not secret)")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", help="PostgreSQL user (not secret)")
    parser.add_argument("--database-name", default="postgres")
    parser.add_argument(
        "--prompt-password",
        action="store_true",
        help="Read the database password privately without echoing or shell history",
    )


def connection_arguments(args: argparse.Namespace) -> tuple[tuple[Any, ...], dict[str, Any]]:
    common: dict[str, Any] = {"sslmode": "require", "connect_timeout": 10}
    if args.prompt_password:
        if not args.host or not args.user:
            raise SystemExit("--prompt-password requires --host and --user")
        password = getpass.getpass("Database password (input hidden): ")
        if not password:
            raise SystemExit("Database password was empty")
        return (), {
            **common,
            "host": args.host,
            "port": args.port,
            "user": args.user,
            "password": password,
            "dbname": args.database_name,
        }

    value = os.environ.get(args.database_url_env, "").strip()
    if not value:
        raise SystemExit(
            f"Set {args.database_url_env}, or use --host, --user and --prompt-password"
        )
    if not value.lower().startswith(("postgresql://", "postgres://")):
        raise SystemExit(f"{args.database_url_env} is not a PostgreSQL URL")
    return (value,), common
