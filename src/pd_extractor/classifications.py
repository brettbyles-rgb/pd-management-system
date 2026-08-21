from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .database import connect_database, initialise_database


@dataclass(frozen=True)
class ClassificationMetadata:
    raw_label: str
    display_label: str
    abbreviation: str
    cohort: str
    seniority_order: float | None
    enterprise_agreement: str
    notes: str


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _title_case_tafe(value: str) -> str:
    value = re.sub(r"(?i)\btafe\b", "TAFE", value)
    value = re.sub(r"(?i)\bworker\b", "Worker", value)
    value = re.sub(r"(?i)\bmanager\b", "Manager", value)
    value = re.sub(r"(?i)\blevel\b", "Level", value)
    return value


def _cohort_for_order(order: float | None) -> str:
    if order is None:
        return "Other / Unclassified"
    if order <= 40:
        return "TWL1-TWL4"
    if order <= 70:
        return "TWL5-TWL7"
    if order <= 100:
        return "TWL8-TM1"
    if order <= 130:
        return "TM2-TM4"
    if order <= 150:
        return "TM5-TM6"
    if order <= 180:
        return "Senior Executive"
    return "Other / Specialist"


def infer_classification_metadata(raw_label: str) -> ClassificationMetadata:
    raw = _clean(raw_label)
    fixed = raw
    notes = []
    fixed = re.sub(r"(?i)\bManger\b", "Manager", fixed)
    fixed = re.sub(r"(?i)\bWoker\b", "Worker", fixed)
    if fixed != raw:
        notes.append("Possible typo normalised")
    fixed = _title_case_tafe(fixed)

    abbreviation = ""
    order: float | None = None
    agreement = ""
    display = fixed

    worker = re.search(r"(?i)\bTAFE\s+Worker\s+Level\s+(\d+)\b", fixed)
    if worker:
        level = int(worker.group(1))
        display = f"TAFE Worker Level {level}"
        abbreviation = f"TWL{level}"
        order = level * 10
        agreement = "TAFE Commission of NSW Administrative, Support and Related Employees Enterprise Agreement"

    manager = re.search(r"(?i)\bTAFE\s+Manager(?:\s+Level)?\s+(\d+)\b", fixed)
    if manager:
        level = int(manager.group(1))
        display = f"TAFE Manager Level {level}"
        abbreviation = f"TM{level}"
        order = 90 + (level * 10)
        agreement = "TAFE Managers Enterprise Agreement"

    psse = re.search(r"(?i)\bPSSE\s+Band\s+(\d+)\b", fixed)
    if psse:
        band = int(psse.group(1))
        display = f"PSSE Band {band}" if "/" not in fixed else fixed
        abbreviation = f"PSSE{band}"
        order = 150 + (band * 10)
        agreement = "Public Service Senior Executives"

    seo_like = {
        "Education Officer": ("EO", 74),
        "Senior Education Officer": ("SEO", 84),
        "Chief Education Officer": ("CEO", 94),
        "Principal Education Officer": ("PEO", 104),
    }
    if fixed in seo_like:
        abbreviation, order = seo_like[fixed]
        agreement = "Educational Services"

    librarian = re.search(r"(?i)\bLibrar(?:ian|y Technician|ian Technician)\s+Grade\s+(\d+)\b", fixed)
    if librarian:
        grade = int(librarian.group(1))
        if "technician" in fixed.lower():
            display = "Library Technician Grade 1" if grade == 1 else fixed
            abbreviation = f"LTG{grade}"
        else:
            display = f"Librarian Grade {grade}"
            abbreviation = f"LG{grade}"
        order = 50 + (grade * 10)
        agreement = "Specialist / legacy classification"

    if re.fullmatch(r"\d{5}-\d{2}", fixed):
        notes.append("Looks like a PD number, not a classification")

    return ClassificationMetadata(
        raw_label=raw,
        display_label=display,
        abbreviation=abbreviation,
        cohort=_cohort_for_order(order),
        seniority_order=order,
        enterprise_agreement=agreement,
        notes="; ".join(notes),
    )


def seed_classification_references(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        """SELECT classification_grade_band AS raw_label, COUNT(*) AS usage_count
           FROM position_descriptions
           WHERE COALESCE(TRIM(classification_grade_band), '') <> ''
           GROUP BY classification_grade_band
           ORDER BY usage_count DESC, raw_label"""
    ).fetchall()
    inserted = 0
    with connection:
        for row in rows:
            meta = infer_classification_metadata(row["raw_label"])
            changed = connection.execute(
                """INSERT OR IGNORE INTO classification_references(
                    raw_label, display_label, abbreviation, cohort, seniority_order,
                    enterprise_agreement, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    meta.raw_label,
                    meta.display_label,
                    meta.abbreviation,
                    meta.cohort,
                    meta.seniority_order,
                    meta.enterprise_agreement,
                    meta.notes,
                ),
            ).rowcount
            inserted += changed
    return {"raw_classifications": len(rows), "inserted": inserted}


def classification_rows(connection: sqlite3.Connection) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(
            """SELECT cr.*, COUNT(pd.id) AS usage_count
               FROM classification_references cr
               LEFT JOIN position_descriptions pd ON pd.classification_grade_band = cr.raw_label
               GROUP BY cr.id
               ORDER BY
                    CASE WHEN cr.seniority_order IS NULL THEN 1 ELSE 0 END,
                    cr.seniority_order,
                    cr.display_label,
                    cr.raw_label"""
        )
    ]


def update_classification_references(connection: sqlite3.Connection, rows: list[dict]) -> int:
    with connection:
        for row in rows:
            connection.execute(
                """UPDATE classification_references SET
                    display_label = ?,
                    abbreviation = ?,
                    cohort = ?,
                    seniority_order = ?,
                    enterprise_agreement = ?,
                    active = ?,
                    notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                   WHERE raw_label = ?""",
                (
                    _clean(row.get("display_label")),
                    _clean(row.get("abbreviation")),
                    _clean(row.get("cohort")),
                    row.get("seniority_order") if row.get("seniority_order") not in ("", None) else None,
                    _clean(row.get("enterprise_agreement")),
                    1 if row.get("active", True) else 0,
                    _clean(row.get("notes")),
                    _clean(row.get("raw_label")),
                ),
            )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed classification reference data from imported PDs")
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args()
    connection = connect_database(args.database)
    try:
        initialise_database(connection)
        summary = seed_classification_references(connection)
    finally:
        connection.close()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
