from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import connect_database, initialise_database


GENERATOR_VERSION = "mapping-text-v1"

ACCOUNTABILITY_BOILERPLATE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "customer-centred decision boilerplate",
        re.compile(r"\bplace the customer at the centre of all decision making\b", re.I),
    ),
    (
        "safety leadership boilerplate",
        re.compile(
            r"\b(safety excellence|safety leadership|safe workplace|safety systems and procedures)\b",
            re.I,
        ),
    ),
    (
        "high-performance team boilerplate",
        re.compile(
            r"\b(high[- ]performance team|core values of integrity,\s*collaboration,\s*excellence|"
            r"through effective leadership,\s*support and feedback)\b",
            re.I,
        ),
    ),
    (
        "performance review/development plan boilerplate",
        re.compile(
            r"\b(individual performance management and development plans|"
            r"performance management and development plans|regular review of meaningful individual performance)\b",
            re.I,
        ),
    ),
]

MANDATORY_KEY_ACCOUNTABILITIES = {
    "Reflect TAFE NSW’s values in the way you work and abide by policies and procedures to ensure a safe, healthy and inclusive work environment.",
    "Place the customer at the centre of all decision making.",
    "Work with the Line Manager to develop and review meaningful performance development and review plans.",
    "Demonstrate a genuine commitment to safety excellence and safety leadership. This includes setting health and safety expectations, results and behaviours with direct reports, providing a safe workplace and ways of working, and promoting and complying with safety systems and procedures.",
    "Manage and develop a high performance team, aligned to the core values of integrity, collaboration, excellence and a customer first attitude, through effective leadership, support and feedback.",
    "Collaborate with staff to ensure the development and regular review of meaningful individual performance development and review plans that are clearly aligned to strategic objectives and focused to develop the individual.",
}

MANDATORY_ESSENTIAL_REQUIREMENTS = {
    "A Valid Working with Children Check (required prior to commencement).",
    "Undergraduate or postgraduate degree qualification in a relevant discipline, completed within the previous two years or due to be completed in the current year.",
    "Appropriate Degree or Diploma at AQF level 5-8 or equivalent, and appropriate vocational and/or industrial experience.",
    "Certificate III in a relevant discipline or equivalent skills, knowledge and experience.",
    "Certificate IV in relevant discipline or equivalent skills, knowledge and experience.",
    "Diploma, Advanced Diploma or Associate Degree in a relevant discipline or equivalent skills, knowledge and experience.",
    "Degree in a relevant discipline or equivalent skills, knowledge and experience.",
    "Aboriginality is a genuine occupational qualification and is authorised under Section 14 of the Anti-Discrimination Act 1977. Candidates selected for an interview must provide Confirmation of Aboriginality documentation at or before interview.",
}

MANDATORY_KEY_ACCOUNTABILITY_KEYS = set()
MANDATORY_ESSENTIAL_REQUIREMENT_KEYS = set()


@dataclass(frozen=True)
class MappingTextRecord:
    position_description_id: int
    title_text: str
    purpose_text: str
    accountabilities_text: str
    knowledge_text: str
    requirements_text: str
    full_text: str
    excluded_items: list[dict[str, Any]]


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _fingerprint(value: str | None) -> str:
    text = _clean(value).lower()
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return _clean(text)


MANDATORY_KEY_ACCOUNTABILITY_KEYS = {
    _fingerprint(item) for item in MANDATORY_KEY_ACCOUNTABILITIES
}
MANDATORY_ESSENTIAL_REQUIREMENT_KEYS = {
    _fingerprint(item) for item in MANDATORY_ESSENTIAL_REQUIREMENTS
}


def _join_items(items: list[str]) -> str:
    return "\n".join(f"- {_clean(item)}" for item in items if _clean(item))


def _is_boilerplate_accountability(text: str) -> str | None:
    cleaned = _clean(text)
    if _fingerprint(cleaned) in MANDATORY_KEY_ACCOUNTABILITY_KEYS:
        return "mandatory key accountability boilerplate"
    for reason, pattern in ACCOUNTABILITY_BOILERPLATE_PATTERNS:
        if pattern.search(cleaned):
            return reason
    return None


def _is_boilerplate_requirement(text: str) -> str | None:
    cleaned = _clean(text)
    if _fingerprint(cleaned) in MANDATORY_ESSENTIAL_REQUIREMENT_KEYS:
        return "mandatory essential requirement boilerplate"
    return None


def _pd_list_items(connection: sqlite3.Connection, pd_id: int, section_name: str) -> list[sqlite3.Row]:
    return connection.execute(
        """SELECT sequence, item_text
           FROM pd_list_items
           WHERE position_description_id = ? AND section_name = ?
           ORDER BY sequence""",
        (pd_id, section_name),
    ).fetchall()


def _pd_section(connection: sqlite3.Connection, pd_id: int, section_name: str) -> str:
    row = connection.execute(
        """SELECT section_text
           FROM pd_sections
           WHERE position_description_id = ? AND section_name = ?""",
        (pd_id, section_name),
    ).fetchone()
    return _clean(row["section_text"]) if row else ""


def build_mapping_text_record(connection: sqlite3.Connection, pd_id: int) -> MappingTextRecord:
    pd = connection.execute(
        """SELECT id, role_title
           FROM position_descriptions
           WHERE id = ?""",
        (pd_id,),
    ).fetchone()
    if pd is None:
        raise KeyError(pd_id)

    excluded: list[dict[str, Any]] = []
    accountabilities = []
    for row in _pd_list_items(connection, pd_id, "key_accountabilities"):
        text = _clean(row["item_text"])
        reason = _is_boilerplate_accountability(text)
        if reason:
            excluded.append({
                "section": "key_accountabilities",
                "sequence": row["sequence"],
                "reason": reason,
                "text": text,
            })
        else:
            accountabilities.append(text)

    requirements = []
    for row in _pd_list_items(connection, pd_id, "essential_requirements"):
        text = _clean(row["item_text"])
        reason = _is_boilerplate_requirement(text)
        if reason:
            excluded.append({
                "section": "essential_requirements",
                "sequence": row["sequence"],
                "reason": reason,
                "text": text,
            })
        else:
            requirements.append(text)

    title = _clean(pd["role_title"])
    purpose = _pd_section(connection, pd_id, "primary_purpose")
    knowledge = [_clean(row["item_text"]) for row in _pd_list_items(
        connection, pd_id, "key_knowledge_and_experience"
    )]

    sections = [
        ("Role title", title),
        ("Primary purpose", purpose),
        ("Key accountabilities", _join_items(accountabilities)),
        ("Key knowledge and experience", _join_items(knowledge)),
        ("Essential requirements", _join_items(requirements)),
    ]
    full_text = "\n\n".join(f"{heading}:\n{text}" for heading, text in sections if text)

    return MappingTextRecord(
        position_description_id=pd_id,
        title_text=title,
        purpose_text=purpose,
        accountabilities_text=_join_items(accountabilities),
        knowledge_text=_join_items(knowledge),
        requirements_text=_join_items(requirements),
        full_text=full_text,
        excluded_items=excluded,
    )


def upsert_mapping_text(connection: sqlite3.Connection, record: MappingTextRecord) -> None:
    connection.execute(
        """INSERT INTO pd_mapping_texts(
            position_description_id, generator_version, title_text, purpose_text,
            accountabilities_text, knowledge_text, requirements_text, full_text,
            excluded_items_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(position_description_id) DO UPDATE SET
            generator_version = excluded.generator_version,
            title_text = excluded.title_text,
            purpose_text = excluded.purpose_text,
            accountabilities_text = excluded.accountabilities_text,
            knowledge_text = excluded.knowledge_text,
            requirements_text = excluded.requirements_text,
            full_text = excluded.full_text,
            excluded_items_json = excluded.excluded_items_json,
            created_at = CURRENT_TIMESTAMP""",
        (
            record.position_description_id,
            GENERATOR_VERSION,
            record.title_text,
            record.purpose_text,
            record.accountabilities_text,
            record.knowledge_text,
            record.requirements_text,
            record.full_text,
            json.dumps(record.excluded_items, ensure_ascii=False),
        ),
    )


def generate_mapping_texts(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute("SELECT id FROM position_descriptions ORDER BY id").fetchall()
    generated = 0
    excluded = 0
    with connection:
        for row in rows:
            record = build_mapping_text_record(connection, int(row["id"]))
            upsert_mapping_text(connection, record)
            generated += 1
            excluded += len(record.excluded_items)
    return {"generated": generated, "excluded_items": excluded}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate clean PD mapping text for embeddings")
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args()

    connection = connect_database(args.database)
    try:
        initialise_database(connection)
        summary = generate_mapping_texts(connection)
    finally:
        connection.close()
    print(json.dumps({"generator_version": GENERATOR_VERSION, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
