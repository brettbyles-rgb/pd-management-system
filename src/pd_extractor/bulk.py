from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import (
    connect_database,
    database_statistics,
    generate_database_report,
    import_document,
    initialise_database,
)
from .extractor import extract_document


@dataclass(frozen=True)
class BulkRunSummary:
    discovered: int
    attempted: int
    extracted: int
    failed: int
    imported: int
    output_dir: Path
    database: Path
    summary_json: Path
    summary_csv: Path


def _safe_json_name(document: Path) -> str:
    return f"{document.stem}.json"


def _row_for_success(document: Path, result: dict[str, Any], imported: bool) -> dict[str, Any]:
    record = result.get("pd_record", {})
    return {
        "source_filename": document.name,
        "status": "extracted",
        "imported": "yes" if imported else "no",
        "role_title": record.get("role_title", ""),
        "position_description_no": result.get("role_description_fields", {}).get(
            "position_description_no", ""
        ),
        "extraction_status": record.get("extraction_status", ""),
        "accountabilities": len(result.get("key_accountabilities", [])),
        "challenges": len(result.get("key_challenges", [])),
        "relationships": len(result.get("key_relationships", [])),
        "requirements": len(result.get("essential_requirements", [])),
        "capabilities": len(result.get("capabilities", [])),
        "issues": len(result.get("extraction_issues", [])),
        "error_type": "",
        "error": "",
    }


def _row_for_failure(document: Path, error: Exception) -> dict[str, Any]:
    return {
        "source_filename": document.name,
        "status": "failed",
        "imported": "no",
        "role_title": "",
        "position_description_no": "",
        "extraction_status": "",
        "accountabilities": "",
        "challenges": "",
        "relationships": "",
        "requirements": "",
        "capabilities": "",
        "issues": "",
        "error_type": error.__class__.__name__,
        "error": str(error),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_bulk_import(
    source_dir: Path,
    output_dir: Path,
    database: Path,
    *,
    limit: int | None = None,
    overwrite_database: bool = False,
    report: Path | None = None,
) -> BulkRunSummary:
    documents = sorted(
        path for path in source_dir.glob("*.docx")
        if not path.name.startswith("~$")
    )
    selected = documents[:limit] if limit else documents
    output_dir.mkdir(parents=True, exist_ok=True)

    if overwrite_database and database.exists():
        database.unlink()

    connection = connect_database(database)
    rows: list[dict[str, Any]] = []
    imported = 0
    try:
        initialise_database(connection)
        for index, document in enumerate(selected, 1):
            print(f"[{index}/{len(selected)}] {document.name}", flush=True)
            try:
                result = extract_document(document)
                (output_dir / _safe_json_name(document)).write_text(
                    json.dumps(result, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                import_document(connection, result)
                imported += 1
                rows.append(_row_for_success(document, result, imported=True))
            except Exception as error:
                rows.append(_row_for_failure(document, error))
        if report:
            generate_database_report(connection, report)
        stats = database_statistics(connection)
    finally:
        connection.close()

    summary = {
        "source_dir": str(source_dir),
        "database": str(database),
        "output_dir": str(output_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "discovered": len(documents),
        "attempted": len(selected),
        "extracted": sum(1 for row in rows if row["status"] == "extracted"),
        "failed": sum(1 for row in rows if row["status"] == "failed"),
        "imported": imported,
        "database_statistics": stats,
        "rows": rows,
    }
    summary_json = output_dir / "_bulk_summary.json"
    summary_csv = output_dir / "_bulk_summary.csv"
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(summary_csv, rows)

    return BulkRunSummary(
        discovered=len(documents),
        attempted=len(selected),
        extracted=summary["extracted"],
        failed=summary["failed"],
        imported=imported,
        output_dir=output_dir,
        database=database,
        summary_json=summary_json,
        summary_csv=summary_csv,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk extract Word PDs and import the successful results into SQLite"
    )
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output/bulk-json"))
    parser.add_argument("--database", type=Path, default=Path("output/pd-management-bulk.sqlite3"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite-database", action="store_true")
    parser.add_argument("--backup-existing", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("output/bulk-database-summary.html"))
    args = parser.parse_args()

    if args.backup_existing and args.database.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = args.database.with_name(f"{args.database.stem}-backup-{timestamp}{args.database.suffix}")
        shutil.copy2(args.database, backup)
        print(f"Backed up existing database to {backup}")

    summary = run_bulk_import(
        args.source_dir,
        args.output_dir,
        args.database,
        limit=args.limit,
        overwrite_database=args.overwrite_database,
        report=args.report,
    )
    print(
        json.dumps(
            {
                "discovered": summary.discovered,
                "attempted": summary.attempted,
                "extracted": summary.extracted,
                "failed": summary.failed,
                "imported": summary.imported,
                "database": str(summary.database),
                "summary_json": str(summary.summary_json),
                "summary_csv": str(summary.summary_csv),
                "report": str(args.report),
            },
            indent=2,
        )
    )
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
