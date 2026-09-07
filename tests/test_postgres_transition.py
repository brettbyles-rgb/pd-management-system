from pathlib import Path

import pytest

from pd_extractor.config import WebSettings, web_settings
from pd_extractor.database import _postgres_parameters
from pd_extractor.embeddings import DEFAULT_MODEL_NAME
from pd_extractor.web_app import create_app


ROOT = Path(__file__).resolve().parents[1]


def test_postgres_url_is_loaded_without_displacing_local_fallback(monkeypatch):
    monkeypatch.setenv(
        "PD_MANAGEMENT_DATABASE_URL",
        "postgresql://application:secret@example.invalid:5432/postgres",
    )
    settings = web_settings()

    assert settings.database_url.startswith("postgresql://")
    assert settings.database_path.name == "pd_management_unified.sqlite3"


def test_qmark_translation_ignores_quoted_question_marks():
    sql = "SELECT '?' AS literal, value FROM roles WHERE id = ? AND note = \"?\""
    assert _postgres_parameters(sql) == (
        "SELECT '?' AS literal, value FROM roles WHERE id = %s AND note = \"?\""
    )


def test_postgres_is_guarded_to_read_only_explorer_profile(tmp_path):
    settings = WebSettings(
        database_path=tmp_path / "unused.sqlite3",
        model_name=DEFAULT_MODEL_NAME,
        deployment_profile="full",
        database_url="postgresql://application:secret@example.invalid/postgres",
    )

    with pytest.raises(ValueError, match="read-only explorer-demo"):
        create_app(settings)


def test_postgres_migrations_exclude_sqlite_only_syntax():
    migrations = sorted((ROOT / "migrations" / "postgresql").glob("*.sql"))
    assert migrations
    sql = "\n".join(path.read_text(encoding="utf-8") for path in migrations).upper()

    assert "PRAGMA " not in sql
    assert "SQLITE_MASTER" not in sql
    assert "INSERT OR REPLACE" not in sql
    assert "INSERT OR IGNORE" not in sql


def test_admin_read_model_migration_is_present_and_protected():
    migration = (
        ROOT / "migrations" / "postgresql" / "0002_admin_read_model.sql"
    ).read_text(encoding="utf-8")

    for table in (
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
    ):
        assert f"CREATE TABLE {table}" in migration
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in migration
    assert "DEFAULT CURRENT_TIMESTAMP," not in migration
    assert "DEFAULT CURRENT_TIMESTAMP\n" not in migration


def test_postgres_copy_uses_cursor_for_bulk_inserts():
    script = (ROOT / "scripts" / "copy_explorer_to_postgres.py").read_text(
        encoding="utf-8"
    )

    assert "with target.cursor() as writer:" in script
    assert "writer.executemany(" in script
    assert "target.executemany(" not in script


def test_explorer_queries_do_not_mix_text_and_numeric_coalesce_types():
    source = (
        ROOT / "src" / "pd_extractor" / "career_explorer_reference_data.py"
    ).read_text(encoding="utf-8")

    assert "COALESCE(s.share,'0')" in source
    assert "COALESCE(s.share,0)" not in source
