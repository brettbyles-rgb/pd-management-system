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
    password_mode = parser.add_mutually_exclusive_group()
    password_mode.add_argument(
        "--prompt-password",
        action="store_true",
        help="Read the database password privately without echoing or shell history",
    )
    password_mode.add_argument(
        "--visible-password",
        action="store_true",
        help="Read the database password visibly (not stored in shell history)",
    )


def connection_arguments(
    args: argparse.Namespace,
) -> tuple[tuple[Any, ...], dict[str, Any], str | None]:
    common: dict[str, Any] = {"sslmode": "require", "connect_timeout": 10}
    visible_password = getattr(args, "visible_password", False)
    if args.prompt_password or visible_password:
        if not args.host or not args.user:
            raise SystemExit("Password prompting requires --host and --user")
        if visible_password:
            print(
                "Paste the password below. It will be VISIBLE so you can check it. "
                "Surrounding spaces will be removed."
            )
            raw_password = input("Database password (VISIBLE): ")
        else:
            raw_password = getpass.getpass("Database password (input hidden): ")
        password = raw_password.strip()
        if not password:
            raise SystemExit("Database password was empty")
        trimmed = len(raw_password) - len(password)
        if not visible_password:
            raw_confirmation = getpass.getpass("Paste the same password again (input hidden): ")
            confirmation = raw_confirmation.strip()
            if password != confirmation:
                raise SystemExit("The two password entries did not match; connection not attempted")
            trimmed += len(raw_confirmation) - len(confirmation)
        if trimmed:
            print(f"Removed {trimmed} surrounding whitespace character(s).")
        print(f"Password accepted ({len(password)} characters); connecting securely...")
        return (), {
            **common,
            "host": args.host,
            "port": args.port,
            "user": args.user,
            "dbname": args.database_name,
        }, password

    value = os.environ.get(args.database_url_env, "").strip()
    if not value:
        raise SystemExit(
            f"Set {args.database_url_env}, or use --host, --user and a password prompt option"
        )
    if not value.lower().startswith(("postgresql://", "postgres://")):
        raise SystemExit(f"{args.database_url_env} is not a PostgreSQL URL")
    return (value,), common, None


def open_postgres_connection(psycopg: Any, args: argparse.Namespace) -> Any:
    positional, keywords, prompted_password = connection_arguments(args)
    prior_password = os.environ.get("PGPASSWORD")
    try:
        if prompted_password is not None:
            # libpq reads this directly. It is removed immediately after the connection
            # attempt and cannot be interpolated into a diagnostic connection string.
            os.environ["PGPASSWORD"] = prompted_password
        return psycopg.connect(*positional, **keywords)
    except psycopg.Error:
        raise SystemExit(
            "Database connection failed. Detailed connection diagnostics were suppressed "
            "because they can contain credentials. Check the host, user and password."
        ) from None
    finally:
        if prompted_password is not None:
            if prior_password is None:
                os.environ.pop("PGPASSWORD", None)
            else:
                os.environ["PGPASSWORD"] = prior_password
