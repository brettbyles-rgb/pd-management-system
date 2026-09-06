from __future__ import annotations

import argparse
import html
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable


CANONICAL_FRAMEWORKS = [
    "NSW Public Sector Capability Framework",
    "Asset management",
    "Finance",
    "Human resources",
    "Infrastructure and Construction Project Leader (ICPL)",
    "Information and Communication Technology (ICT)",
    "Legal",
    "Procurement",
    "Property acquisition",
]

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS position_descriptions (
    id INTEGER PRIMARY KEY,
    source_filename TEXT NOT NULL UNIQUE,
    role_title TEXT NOT NULL,
    position_description_no TEXT,
    extraction_status TEXT NOT NULL,
    department_agency TEXT,
    division_branch_unit TEXT,
    classification_grade_band TEXT,
    anzsco_code TEXT,
    osca_code TEXT,
    pcat_code TEXT,
    date_of_approval TEXT,
    senior_executive_work_level_standards TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_description_fields (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    field_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pd_sections (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    section_text TEXT NOT NULL,
    UNIQUE(position_description_id, section_name)
);

CREATE TABLE IF NOT EXISTS pd_list_items (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    item_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_relationships (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    relationship_group TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    who TEXT NOT NULL,
    why TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capability_frameworks (
    id INTEGER PRIMARY KEY,
    framework_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS capability_definitions (
    id INTEGER PRIMARY KEY,
    framework_id INTEGER NOT NULL REFERENCES capability_frameworks(id),
    capability_name TEXT NOT NULL,
    capability_code TEXT,
    UNIQUE(framework_id, capability_name)
);

CREATE TABLE IF NOT EXISTS pd_capabilities (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    capability_definition_id INTEGER NOT NULL REFERENCES capability_definitions(id),
    sequence INTEGER NOT NULL,
    capability_type TEXT NOT NULL,
    required_level TEXT NOT NULL,
    capability_group TEXT,
    description TEXT,
    source_text TEXT
);

CREATE TABLE IF NOT EXISTS capability_indicators (
    id INTEGER PRIMARY KEY,
    pd_capability_id INTEGER NOT NULL REFERENCES pd_capabilities(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    indicator_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_issues (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    issue_type TEXT NOT NULL,
    field_or_section TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_records (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL UNIQUE REFERENCES position_descriptions(id) ON DELETE CASCADE,
    extracted_json TEXT NOT NULL,
    draft_json TEXT NOT NULL,
    section_statuses_json TEXT NOT NULL DEFAULT '{}',
    edited_paths_json TEXT NOT NULL DEFAULT '[]',
    validation_status TEXT NOT NULL DEFAULT 'Not validated',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    validated_at TEXT
);

CREATE TABLE IF NOT EXISTS validation_events (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_family_import_batches (
    id INTEGER PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_path TEXT,
    framework_sheet TEXT NOT NULL,
    mapping_sheet TEXT NOT NULL,
    framework_rows INTEGER NOT NULL DEFAULT 0,
    mapping_rows INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_family_entries (
    id INTEGER PRIMARY KEY,
    import_batch_id INTEGER NOT NULL REFERENCES job_family_import_batches(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    parent_code TEXT,
    main_definition TEXT,
    supp_definition_1 TEXT,
    supp_definition_2 TEXT,
    exclusions TEXT,
    sequence INTEGER NOT NULL,
    UNIQUE(import_batch_id, code)
);

CREATE TABLE IF NOT EXISTS pd_job_family_mappings (
    id INTEGER PRIMARY KEY,
    import_batch_id INTEGER NOT NULL REFERENCES job_family_import_batches(id) ON DELETE CASCADE,
    position_description_id INTEGER REFERENCES position_descriptions(id) ON DELETE SET NULL,
    pd_id TEXT NOT NULL,
    position_title TEXT,
    position_grade TEXT,
    mapping_rank INTEGER NOT NULL,
    mapping_code TEXT,
    mapping_name TEXT,
    mapping_level TEXT,
    mapping_validated TEXT,
    validation_notes TEXT,
    framework_code_valid INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pd_assigned_job_family_mappings (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    mapping_rank INTEGER NOT NULL CHECK(mapping_rank BETWEEN 1 AND 3),
    mapping_code TEXT NOT NULL,
    mapping_name TEXT NOT NULL,
    mapping_level TEXT NOT NULL,
    mapping_validated TEXT NOT NULL DEFAULT 'Yes',
    validation_notes TEXT,
    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(position_description_id, mapping_rank),
    UNIQUE(position_description_id, mapping_code)
);

CREATE TABLE IF NOT EXISTS pd_mapping_texts (
    id INTEGER PRIMARY KEY,
    position_description_id INTEGER NOT NULL UNIQUE REFERENCES position_descriptions(id) ON DELETE CASCADE,
    generator_version TEXT NOT NULL,
    title_text TEXT NOT NULL,
    purpose_text TEXT NOT NULL,
    accountabilities_text TEXT NOT NULL,
    knowledge_text TEXT NOT NULL,
    requirements_text TEXT NOT NULL,
    full_text TEXT NOT NULL,
    excluded_items_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    source_text_hash TEXT NOT NULL,
    source_text TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_type, source_id, model_name)
);

CREATE TABLE IF NOT EXISTS classification_references (
    id INTEGER PRIMARY KEY,
    raw_label TEXT NOT NULL UNIQUE,
    display_label TEXT NOT NULL,
    abbreviation TEXT,
    cohort TEXT,
    seniority_order REAL,
    enterprise_agreement TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pd_list_items_position ON pd_list_items(position_description_id, section_name);
CREATE INDEX IF NOT EXISTS idx_relationships_position ON key_relationships(position_description_id);
CREATE INDEX IF NOT EXISTS idx_pd_capabilities_position ON pd_capabilities(position_description_id);
CREATE INDEX IF NOT EXISTS idx_capability_definitions_framework ON capability_definitions(framework_id);
CREATE INDEX IF NOT EXISTS idx_job_family_entries_batch_code ON job_family_entries(import_batch_id, code);
CREATE INDEX IF NOT EXISTS idx_pd_job_family_mappings_batch_pd ON pd_job_family_mappings(import_batch_id, pd_id);
CREATE INDEX IF NOT EXISTS idx_pd_job_family_mappings_position ON pd_job_family_mappings(position_description_id);
CREATE INDEX IF NOT EXISTS idx_pd_assigned_job_family_mappings_position ON pd_assigned_job_family_mappings(position_description_id);
CREATE INDEX IF NOT EXISTS idx_pd_mapping_texts_position ON pd_mapping_texts(position_description_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_source ON embeddings(source_type, source_id, model_name);
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model_name);
CREATE INDEX IF NOT EXISTS idx_classification_references_raw ON classification_references(raw_label);
CREATE INDEX IF NOT EXISTS idx_classification_references_order ON classification_references(cohort, seniority_order);

CREATE VIEW IF NOT EXISTS pd_capabilities_readable AS
SELECT
    pc.id AS pd_capability_id,
    pd.id AS position_description_id,
    pd.role_title,
    pd.position_description_no,
    pc.sequence,
    pc.capability_type,
    cf.framework_name AS framework,
    cd.capability_name,
    cd.capability_code,
    pc.required_level,
    pc.capability_group,
    pc.description,
    pc.source_text
FROM pd_capabilities pc
JOIN position_descriptions pd ON pd.id = pc.position_description_id
JOIN capability_definitions cd ON cd.id = pc.capability_definition_id
JOIN capability_frameworks cf ON cf.id = cd.framework_id;

CREATE VIEW IF NOT EXISTS active_job_family_entries AS
SELECT entry.*
FROM job_family_entries entry
JOIN job_family_import_batches batch ON batch.id = entry.import_batch_id
WHERE batch.is_active = 1;

CREATE VIEW IF NOT EXISTS active_pd_job_family_mappings AS
SELECT mapping.id, mapping.import_batch_id, mapping.position_description_id,
       mapping.pd_id, mapping.position_title, mapping.position_grade,
       mapping.mapping_rank, mapping.mapping_code, mapping.mapping_name,
       mapping.mapping_level, mapping.mapping_validated,
       mapping.validation_notes, mapping.framework_code_valid
FROM pd_job_family_mappings mapping
JOIN job_family_import_batches batch ON batch.id = mapping.import_batch_id
WHERE batch.is_active = 1
  AND NOT EXISTS (
      SELECT 1 FROM pd_assigned_job_family_mappings assigned
      WHERE assigned.position_description_id = mapping.position_description_id
  )
UNION ALL
SELECT -assigned.id AS id, NULL AS import_batch_id, assigned.position_description_id,
       SUBSTR(pd.position_description_no, 1, 5) AS pd_id,
       pd.role_title AS position_title,
       pd.classification_grade_band AS position_grade,
       assigned.mapping_rank, assigned.mapping_code, assigned.mapping_name,
       assigned.mapping_level, assigned.mapping_validated,
       assigned.validation_notes, 1 AS framework_code_valid
FROM pd_assigned_job_family_mappings assigned
JOIN position_descriptions pd ON pd.id = assigned.position_description_id;
"""


@runtime_checkable
class DatabaseConnection(Protocol):
    """Small DB-API surface shared by SQLite and the read-only PostgreSQL slice."""

    backend: str

    def execute(self, sql: str, parameters: object = ...) -> Any: ...
    def executemany(self, sql: str, parameters: object) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


def _postgres_parameters(sql: str) -> str:
    """Translate SQLite qmark parameters without changing quoted question marks."""
    output: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(sql):
        character = sql[index]
        if quote:
            output.append(character)
            if character == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    output.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            output.append(character)
        elif character == "?":
            output.append("%s")
        else:
            output.append(character)
        index += 1
    return "".join(output)


class PostgresConnection:
    """Compatibility wrapper for the SQL used by the read-only Explorer routes."""

    backend = "postgresql"

    def __init__(self, connection: Any):
        self._connection = connection

    def execute(self, sql: str, parameters: object = ()) -> Any:
        return self._connection.execute(_postgres_parameters(sql), parameters)

    def executemany(self, sql: str, parameters: object) -> Any:
        return self._connection.executemany(_postgres_parameters(sql), parameters)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PostgresConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> object:
        return self._connection.__exit__(exc_type, exc, traceback)


def connect_database(
    path: Path,
    database_url: str | None = None,
) -> sqlite3.Connection | PostgresConnection:
    if database_url:
        if not database_url.lower().startswith(("postgresql://", "postgres://")):
            raise ValueError("PD_MANAGEMENT_DATABASE_URL must be a PostgreSQL connection URL")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - exercised only in a misbuilt runtime
            raise RuntimeError("PostgreSQL support requires psycopg") from exc
        connection = psycopg.connect(
            database_url,
            sslmode="require",
            row_factory=dict_row,
            connect_timeout=10,
        )
        return PostgresConnection(connection)

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def database_backend(connection: object) -> str:
    return getattr(connection, "backend", "sqlite")


def database_object_exists(
    connection: sqlite3.Connection | PostgresConnection,
    name: str,
) -> bool:
    if database_backend(connection) == "postgresql":
        row = connection.execute("SELECT to_regclass(?) AS object_name", (name,)).fetchone()
        return bool(row and row["object_name"])
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (name,),
    ).fetchone() is not None


def initialise_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    definition_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(capability_definitions)")
    }
    if "capability_code" not in definition_columns:
        connection.execute("ALTER TABLE capability_definitions ADD COLUMN capability_code TEXT")
    connection.executescript("""
        DROP VIEW IF EXISTS pd_capabilities_readable;
        DROP VIEW IF EXISTS active_job_family_entries;
        DROP VIEW IF EXISTS active_pd_job_family_mappings;
        CREATE VIEW pd_capabilities_readable AS
        SELECT
            pc.id AS pd_capability_id,
            pd.id AS position_description_id,
            pd.role_title,
            pd.position_description_no,
            pc.sequence,
            pc.capability_type,
            cf.framework_name AS framework,
            cd.capability_name,
            cd.capability_code,
            pc.required_level,
            pc.capability_group,
            pc.description,
            pc.source_text
        FROM pd_capabilities pc
        JOIN position_descriptions pd ON pd.id = pc.position_description_id
        JOIN capability_definitions cd ON cd.id = pc.capability_definition_id
        JOIN capability_frameworks cf ON cf.id = cd.framework_id;
        CREATE VIEW active_job_family_entries AS
        SELECT entry.*
        FROM job_family_entries entry
        JOIN job_family_import_batches batch ON batch.id = entry.import_batch_id
        WHERE batch.is_active = 1;
        CREATE VIEW active_pd_job_family_mappings AS
        SELECT mapping.id, mapping.import_batch_id, mapping.position_description_id,
               mapping.pd_id, mapping.position_title, mapping.position_grade,
               mapping.mapping_rank, mapping.mapping_code, mapping.mapping_name,
               mapping.mapping_level, mapping.mapping_validated,
               mapping.validation_notes, mapping.framework_code_valid
        FROM pd_job_family_mappings mapping
        JOIN job_family_import_batches batch ON batch.id = mapping.import_batch_id
        WHERE batch.is_active = 1
          AND NOT EXISTS (
              SELECT 1 FROM pd_assigned_job_family_mappings assigned
              WHERE assigned.position_description_id = mapping.position_description_id
          )
        UNION ALL
        SELECT -assigned.id AS id, NULL AS import_batch_id, assigned.position_description_id,
               SUBSTR(pd.position_description_no, 1, 5) AS pd_id,
               pd.role_title AS position_title,
               pd.classification_grade_band AS position_grade,
               assigned.mapping_rank, assigned.mapping_code, assigned.mapping_name,
               assigned.mapping_level, assigned.mapping_validated,
               assigned.validation_notes, 1 AS framework_code_valid
        FROM pd_assigned_job_family_mappings assigned
        JOIN position_descriptions pd ON pd.id = assigned.position_description_id;
    """)
    connection.executemany(
        "INSERT OR IGNORE INTO capability_frameworks(framework_name) VALUES (?)",
        [(name,) for name in CANONICAL_FRAMEWORKS],
    )
    connection.commit()


def job_family_mappings_for_pd(
    connection: sqlite3.Connection,
    position_description_id: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT mapping_rank, mapping_code, mapping_name, mapping_level,
                  mapping_validated, validation_notes
           FROM active_pd_job_family_mappings
           WHERE position_description_id = ?
           ORDER BY mapping_rank""",
        (position_description_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def assign_job_family_mappings(
    connection: sqlite3.Connection,
    position_description_id: int,
    mapping_codes: list[str],
    *,
    validation_notes: str = "Assigned in Mapping Assistant",
) -> list[dict[str, Any]]:
    codes = list(dict.fromkeys(str(code or "").strip() for code in mapping_codes))
    codes = [code for code in codes if code]
    if not 1 <= len(codes) <= 3:
        raise ValueError("Select between one and three mappings")
    if connection.execute(
        "SELECT 1 FROM position_descriptions WHERE id = ?",
        (position_description_id,),
    ).fetchone() is None:
        raise KeyError(position_description_id)

    placeholders = ",".join("?" for _ in codes)
    entries = connection.execute(
        f"""SELECT code, name, level
            FROM active_job_family_entries
            WHERE code IN ({placeholders})""",
        codes,
    ).fetchall()
    by_code = {str(row["code"]): row for row in entries}
    missing = [code for code in codes if code not in by_code]
    if missing:
        raise ValueError(f"Unknown or inactive framework code: {', '.join(missing)}")

    with connection:
        connection.execute(
            "DELETE FROM pd_assigned_job_family_mappings WHERE position_description_id = ?",
            (position_description_id,),
        )
        connection.executemany(
            """INSERT INTO pd_assigned_job_family_mappings(
                   position_description_id, mapping_rank, mapping_code,
                   mapping_name, mapping_level, mapping_validated, validation_notes
               ) VALUES (?, ?, ?, ?, ?, 'Yes', ?)""",
            [
                (
                    position_description_id,
                    rank,
                    code,
                    by_code[code]["name"],
                    by_code[code]["level"],
                    validation_notes.strip() or "Assigned in Mapping Assistant",
                )
                for rank, code in enumerate(codes, start=1)
            ],
        )
    return job_family_mappings_for_pd(connection, position_description_id)


def _field(fields: dict[str, Any], *names: str) -> str:
    return next((str(fields.get(name) or "") for name in names if fields.get(name)), "")


def import_document(connection: sqlite3.Connection, data: dict[str, Any]) -> int:
    record = data["pd_record"]
    fields = data.get("role_description_fields", {})
    with connection:
        existing = connection.execute(
            "SELECT id FROM position_descriptions WHERE source_filename = ?",
            (record["source_filename"],),
        ).fetchone()
        if existing:
            pd_id = int(existing["id"])
            for table in (
                "role_description_fields", "pd_sections", "pd_list_items",
                "key_relationships", "pd_capabilities", "extraction_issues",
            ):
                connection.execute(f"DELETE FROM {table} WHERE position_description_id = ?", (pd_id,))
            connection.execute(
                """UPDATE position_descriptions SET
                    role_title = ?, position_description_no = ?, extraction_status = ?,
                    department_agency = ?, division_branch_unit = ?, classification_grade_band = ?,
                    anzsco_code = ?, osca_code = ?, pcat_code = ?, date_of_approval = ?,
                    senior_executive_work_level_standards = ?, imported_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (
                    record["role_title"], _field(fields, "position_description_no"),
                    record["extraction_status"], _field(fields, "department_agency"),
                    _field(fields, "division_branch_unit"), _field(fields, "classification_grade_band"),
                    _field(fields, "anzsco_code"), _field(fields, "osca_code"),
                    _field(fields, "pcat_code"), _field(fields, "date_of_approval"),
                    _field(fields, "senior_executive_work_level_standards"), pd_id,
                ),
            )
        else:
            cursor = connection.execute(
                """INSERT INTO position_descriptions(
                source_filename, role_title, position_description_no, extraction_status,
                department_agency, division_branch_unit, classification_grade_band,
                anzsco_code, osca_code, pcat_code, date_of_approval,
                senior_executive_work_level_standards
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["source_filename"], record["role_title"],
                    _field(fields, "position_description_no"), record["extraction_status"],
                    _field(fields, "department_agency"), _field(fields, "division_branch_unit"),
                    _field(fields, "classification_grade_band"), _field(fields, "anzsco_code"),
                    _field(fields, "osca_code"), _field(fields, "pcat_code"),
                    _field(fields, "date_of_approval"),
                    _field(fields, "senior_executive_work_level_standards"),
                ),
            )
            pd_id = int(cursor.lastrowid)

        connection.executemany(
            """INSERT INTO role_description_fields(
                position_description_id, sequence, field_name, field_value
            ) VALUES (?, ?, ?, ?)""",
            [
                (pd_id, item["sequence"], item["field_name"], item["field_value"])
                for item in fields.get("raw_fields", [])
            ],
        )
        connection.executemany(
            "INSERT INTO pd_sections(position_description_id, section_name, section_text) VALUES (?, ?, ?)",
            [(pd_id, name, text) for name, text in data.get("sections", {}).items() if text],
        )
        for section in (
            "key_accountabilities", "key_challenges", "key_knowledge_and_experience",
            "essential_requirements",
        ):
            connection.executemany(
                """INSERT INTO pd_list_items(
                    position_description_id, section_name, sequence, item_text
                ) VALUES (?, ?, ?, ?)""",
                [(pd_id, section, item["sequence"], item["text"]) for item in data.get(section, [])],
            )
        connection.executemany(
            """INSERT INTO key_relationships(
                position_description_id, relationship_group, sequence, who, why
            ) VALUES (?, ?, ?, ?, ?)""",
            [
                (pd_id, item["relationship_group"], item["sequence"], item["who"], item["why"])
                for item in data.get("key_relationships", [])
            ],
        )
        for capability in data.get("capabilities", []):
            framework = capability.get("framework") or "NSW Public Sector Capability Framework"
            framework_id = connection.execute(
                "INSERT OR IGNORE INTO capability_frameworks(framework_name) VALUES (?) RETURNING id",
                (framework,),
            ).fetchone()
            if framework_id is None:
                framework_id = connection.execute(
                    "SELECT id FROM capability_frameworks WHERE framework_name = ?", (framework,)
                ).fetchone()
            definition_id = connection.execute(
                """INSERT OR IGNORE INTO capability_definitions(
                       framework_id, capability_name, capability_code
                   ) VALUES (?, ?, ?) RETURNING id""",
                (
                    framework_id["id"], capability["capability_name"],
                    capability.get("capability_code", ""),
                ),
            ).fetchone()
            if definition_id is None:
                definition_id = connection.execute(
                    """SELECT id FROM capability_definitions
                       WHERE framework_id = ? AND capability_name = ?""",
                    (framework_id["id"], capability["capability_name"]),
                ).fetchone()
                if capability.get("capability_code"):
                    connection.execute(
                        """UPDATE capability_definitions SET capability_code = ?
                           WHERE id = ? AND COALESCE(capability_code, '') = ''""",
                        (capability["capability_code"], definition_id["id"]),
                    )
            pd_capability = connection.execute(
                """INSERT INTO pd_capabilities(
                    position_description_id, capability_definition_id, sequence,
                    capability_type, required_level, capability_group, description, source_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pd_id, definition_id["id"], capability["sequence"],
                    capability["capability_type"], capability.get("level", ""),
                    capability.get("capability_group", ""), capability.get("description", ""),
                    capability.get("source_text", ""),
                ),
            )
            connection.executemany(
                """INSERT INTO capability_indicators(pd_capability_id, sequence, indicator_text)
                   VALUES (?, ?, ?)""",
                [
                    (pd_capability.lastrowid, sequence, indicator)
                    for sequence, indicator in enumerate(capability.get("behavioural_indicators", []), 1)
                ],
            )
        connection.executemany(
            """INSERT INTO extraction_issues(
                position_description_id, issue_type, field_or_section, description, severity
            ) VALUES (?, ?, ?, ?, ?)""",
            [
                (pd_id, item["issue_type"], item["field_or_section"], item["description"], item["severity"])
                for item in data.get("extraction_issues", [])
            ],
        )
        serialized = json.dumps(data, ensure_ascii=False)
        validation = connection.execute(
            "SELECT validation_status, edited_paths_json FROM validation_records WHERE position_description_id = ?",
            (pd_id,),
        ).fetchone()
        if validation is None:
            connection.execute(
                """INSERT INTO validation_records(
                    position_description_id, extracted_json, draft_json
                ) VALUES (?, ?, ?)""",
                (pd_id, serialized, serialized),
            )
        elif validation["validation_status"] == "Not validated" and validation["edited_paths_json"] == "[]":
            connection.execute(
                """UPDATE validation_records SET extracted_json = ?, draft_json = ?,
                   updated_at = CURRENT_TIMESTAMP WHERE position_description_id = ?""",
                (serialized, serialized, pd_id),
            )
        else:
            connection.execute(
                """UPDATE validation_records SET extracted_json = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE position_description_id = ?""",
                (serialized, pd_id),
            )
    return pd_id


def import_json_directory(connection: sqlite3.Connection, json_dir: Path) -> int:
    files = sorted(path for path in json_dir.glob("*.json") if path.name != "_summary.json")
    for path in files:
        import_document(connection, json.loads(path.read_text(encoding="utf-8-sig")))
    return len(files)


def _h(value: object) -> str:
    return html.escape(str(value or ""))


def _table(rows: Iterable[sqlite3.Row], columns: list[tuple[str, str]]) -> str:
    rows = list(rows)
    head = "".join(f"<th>{_h(label)}</th>" for _, label in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_h(row[key])}</td>" for key, _ in columns) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def generate_database_report(connection: sqlite3.Connection, output: Path) -> Path:
    counts = {
        "Position descriptions": connection.execute("SELECT COUNT(*) FROM position_descriptions").fetchone()[0],
        "Relationships": connection.execute("SELECT COUNT(*) FROM key_relationships").fetchone()[0],
        "Capability assignments": connection.execute("SELECT COUNT(*) FROM pd_capabilities").fetchone()[0],
        "Capability definitions": connection.execute("SELECT COUNT(*) FROM capability_definitions").fetchone()[0],
        "Extraction issues": connection.execute("SELECT COUNT(*) FROM extraction_issues").fetchone()[0],
    }
    documents = connection.execute("""
        SELECT pd.role_title, pd.position_description_no, pd.extraction_status,
               COUNT(DISTINCT kr.id) AS relationships,
               COUNT(DISTINCT pc.id) AS capabilities
        FROM position_descriptions pd
        LEFT JOIN key_relationships kr ON kr.position_description_id = pd.id
        LEFT JOIN pd_capabilities pc ON pc.position_description_id = pd.id
        GROUP BY pd.id ORDER BY pd.role_title
    """).fetchall()
    frameworks = connection.execute("""
        SELECT cf.framework_name, COUNT(DISTINCT cd.id) AS definitions,
               COUNT(pc.id) AS assignments
        FROM capability_frameworks cf
        LEFT JOIN capability_definitions cd ON cd.framework_id = cf.id
        LEFT JOIN pd_capabilities pc ON pc.capability_definition_id = cd.id
        GROUP BY cf.id HAVING assignments > 0 ORDER BY cf.framework_name
    """).fetchall()
    cards = "".join(f"<div class=card><b>{value}</b><span>{_h(label)}</span></div>" for label, value in counts.items())
    page = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content=\"width=device-width,initial-scale=1\"><title>PD Database Summary</title>
<style>body{{font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#f4f5f8;color:#172033}}
main{{max-width:1150px;margin:auto;padding:32px}}h1,h2{{color:#351052}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}
.card{{background:#fff;border:1px solid #ddd6e7;border-radius:10px;padding:14px;min-width:170px;display:grid}}
.card b{{font-size:25px;color:#481579}}.card span{{color:#667085}}section{{background:#fff;border:1px solid #dde1e9;border-radius:12px;padding:20px;margin-top:22px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border:1px solid #dde1e9;text-align:left}}th{{background:#f4eff8;color:#481579}}
.table-wrap{{overflow:auto}}</style></head><body><main><h1>Position Description Database</h1>
<p>Validation summary for the imported extractor output.</p><div class=cards>{cards}</div>
<section><h2>Frameworks in use</h2><div class=table-wrap>{_table(frameworks, [("framework_name", "Framework"), ("definitions", "Definitions"), ("assignments", "PD assignments")])}</div></section>
<section><h2>Imported position descriptions</h2><div class=table-wrap>{_table(documents, [("role_title", "Role"), ("position_description_no", "PD number"), ("extraction_status", "Status"), ("relationships", "Relationships"), ("capabilities", "Capabilities")])}</div></section>
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output


def database_statistics(connection: sqlite3.Connection) -> dict[str, int | str]:
    return {
        "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
        "position_descriptions": connection.execute(
            "SELECT COUNT(*) FROM position_descriptions"
        ).fetchone()[0],
        "relationships": connection.execute("SELECT COUNT(*) FROM key_relationships").fetchone()[0],
        "capability_assignments": connection.execute("SELECT COUNT(*) FROM pd_capabilities").fetchone()[0],
        "capability_definitions": connection.execute(
            "SELECT COUNT(*) FROM capability_definitions"
        ).fetchone()[0],
        "behavioural_indicators": connection.execute(
            "SELECT COUNT(*) FROM capability_indicators"
        ).fetchone()[0],
        "extraction_issues": connection.execute("SELECT COUNT(*) FROM extraction_issues").fetchone()[0],
        "job_family_entries": connection.execute(
            "SELECT COUNT(*) FROM active_job_family_entries"
        ).fetchone()[0],
        "pd_job_family_mappings": connection.execute(
            "SELECT COUNT(*) FROM active_pd_job_family_mappings"
        ).fetchone()[0],
        "pd_mapping_texts": connection.execute(
            "SELECT COUNT(*) FROM pd_mapping_texts"
        ).fetchone()[0],
        "embeddings": connection.execute(
            "SELECT COUNT(*) FROM embeddings"
        ).fetchone()[0],
        "classification_references": connection.execute(
            "SELECT COUNT(*) FROM classification_references"
        ).fetchone()[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import extracted PD JSON into SQLite")
    parser.add_argument("json_dir", type=Path)
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--report", type=Path, default=Path("output/database-summary.html"))
    args = parser.parse_args()
    connection = connect_database(args.database)
    try:
        initialise_database(connection)
        count = import_json_directory(connection, args.json_dir)
        generate_database_report(connection, args.report)
        statistics = database_statistics(connection)
    finally:
        connection.close()
    print(f"Imported {count} position descriptions into {args.database}")
    print(json.dumps(statistics, indent=2))
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
