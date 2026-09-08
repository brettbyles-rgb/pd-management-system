import json
from pathlib import Path

from pd_extractor import extract_document
from pd_extractor.database import connect_database, import_document, initialise_database
from pd_extractor.validation_app import (
    APP_VERSION,
    HTML,
    confirm_validation,
    get_validated_export,
    get_validation_record,
    list_validation_records,
    render_validation_app,
    save_validation_draft,
    validation_errors,
)


SAMPLES = Path(__file__).parent / "fixtures"


def _database(tmp_path, filename="10108-01 Alternate Dispute Resolution Specialist - TW9.docx"):
    connection = connect_database(tmp_path / "validation.sqlite3")
    initialise_database(connection)
    import_document(connection, extract_document(SAMPLES / filename))
    return connection


def test_draft_is_separate_from_extracted_snapshot(tmp_path):
    connection = _database(tmp_path)
    try:
        record = get_validation_record(connection, list_validation_records(connection)[0]["id"])
        draft = record["draft"]
        original_title = record["extracted"]["pd_record"]["role_title"]
        draft["pd_record"]["role_title"] = "Edited title"
        save_validation_draft(connection, record["id"], draft, {"role_details": "Confirmed"}, ["role_details"])
        updated = get_validation_record(connection, record["id"])
        assert updated["draft"]["pd_record"]["role_title"] == "Edited title"
        assert updated["extracted"]["pd_record"]["role_title"] == original_title
        assert updated["validation_status"] == "Pending validation"
        assert updated["edited_paths"] == ["role_details"]
    finally:
        connection.close()


def test_confirmation_allows_reviewed_source_exceptions(tmp_path):
    connection = _database(tmp_path, "90001-01 Lead UX Researcher - TM1.docx")
    try:
        record = get_validation_record(connection, list_validation_records(connection)[0]["id"])
        errors = confirm_validation(connection, record["id"], record["draft"], {}, [])
        assert errors == []
        updated = get_validation_record(connection, record["id"])
        assert updated["validation_status"] == "Validated"
        assert updated["draft"]["key_challenges"] == []
        assert any(
            issue["description"] == "Key challenges was not extracted"
            for issue in updated["draft"]["extraction_issues"]
        )
    finally:
        connection.close()


def test_complete_record_can_be_validated(tmp_path):
    connection = _database(tmp_path)
    try:
        record = get_validation_record(connection, list_validation_records(connection)[0]["id"])
        errors = confirm_validation(connection, record["id"], record["draft"], {}, [])
        assert errors == []
        updated = get_validation_record(connection, record["id"])
        assert updated["validation_status"] == "Validated"
        assert updated["validated_at"]
        assert get_validated_export(connection, record["id"])["pd_record"]["role_title"] == "Alternate Dispute Resolution Specialist"
        assert connection.execute("SELECT COUNT(*) FROM validation_events").fetchone()[0] == 1
    finally:
        connection.close()


def test_capability_editor_supports_controlled_add_and_delete():
    assert "+ Add capability" in HTML
    assert "Delete capability" in HTML
    assert "nswCapabilities" in HTML
    assert "capabilityLevels" in HTML
    assert "collectCapabilities" in HTML
    assert "blank-capability" in APP_VERSION
    assert "+ Add metadata row" in HTML
    assert "Delete issue" in HTML
    assert "Mark section reviewed" in HTML
    assert "Validate entire PD" in HTML
    assert "View validated JSON" in HTML
    assert "Download JSON file" in HTML
    assert "PD validated" in HTML
    assert "trusted validated record" in HTML
    assert "capability_type:''" in HTML
    assert "framework:''" in HTML
    assert "capability_name:''" in HTML
    assert "level:''" in HTML


def test_joined_validation_editor_uses_main_service_routes_and_read_only_mode():
    joined = render_validation_app()
    hosted = render_validation_app(read_only=True)

    assert 'href="/validation"' in joined
    assert "/api/validation/pds" in joined
    assert "/validation/source/" in joined
    assert "127.0.0.1:8766" not in joined
    assert "Hosted read-only proof of concept" in hosted
    assert "applyHostedReadOnly" in hosted
