from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from postgres_connection import add_connection_arguments, open_postgres_connection


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pd_extractor.database import PostgresConnection  # noqa: E402
from pd_extractor.reference_workbook import (  # noqa: E402
    apply_reference_workbook,
    validate_reference_workbook,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or atomically apply a governed job-family reference workbook "
            "to PostgreSQL. Preview is the default."
        )
    )
    parser.add_argument("workbook", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the validated workbook; omission performs a read-only preview",
    )
    add_connection_arguments(parser)
    args = parser.parse_args()

    workbook = args.workbook.resolve()
    if not workbook.is_file() or workbook.suffix.lower() != ".xlsx":
        raise SystemExit(f"Workbook does not exist or is not .xlsx: {workbook}")

    import psycopg

    raw_connection = open_postgres_connection(psycopg, args)
    connection = PostgresConnection(raw_connection)
    try:
        preview = validate_reference_workbook(connection, workbook)
        print(json.dumps(preview, indent=2))
        if not preview["valid"]:
            raise SystemExit("Workbook validation failed; no data was changed")
        if not args.apply:
            print("Preview only; use --apply after reviewing the validation report")
            return 0
        result = apply_reference_workbook(connection, workbook)
    finally:
        connection.close()

    print(json.dumps({"applied": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
