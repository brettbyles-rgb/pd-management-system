from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from pd_extractor import extract_document
from pd_extractor.config import WebSettings, web_settings
from pd_extractor.database import connect_database, import_document, initialise_database
from pd_extractor.embeddings import DEFAULT_MODEL_NAME
from pd_extractor.intelligence_app import ADMIN_HTML, HTML_V2
from pd_extractor.web_app import SECURITY_HEADERS, create_app


FIXTURES = Path(__file__).parent / "fixtures"


def client_for(tmp_path):
    settings = WebSettings(
        database_path=tmp_path / "application.sqlite3",
        model_name=DEFAULT_MODEL_NAME,
        environment="test",
    )
    return TestClient(create_app(settings))


def test_health_endpoints_and_security_headers(tmp_path):
    with client_for(tmp_path) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert live.headers["cache-control"] == "no-store"
    assert live.headers["x-request-id"]
    for name, expected in SECURITY_HEADERS.items():
        assert live.headers[name] == expected


def test_existing_html_is_served_without_rewriting(tmp_path):
    with client_for(tmp_path) as client:
        home = client.get("/")
        admin = client.get("/admin/classifications")
        validation = client.get("/validation")
        validation_records = client.get("/api/validation/pds")
        reference_workbook = client.get("/api/reference-data-workbook")
        reference_preview = client.post(
            "/api/reference-data-workbook/preview",
            json={
                "filename": "reference.xlsx",
                "content_base64": base64.b64encode(reference_workbook.content).decode(),
            },
        )

    assert home.status_code == 200
    assert home.text == HTML_V2
    assert admin.status_code == 200
    assert admin.text == ADMIN_HTML
    assert validation.status_code == 200
    assert "PD Validation" in validation.text
    assert "/api/validation/pds" in validation.text
    assert validation_records.status_code == 200
    assert validation_records.json() == []
    assert reference_workbook.status_code == 200
    assert reference_workbook.content.startswith(b"PK")
    assert "pd-reference-data-" in reference_workbook.headers["content-disposition"]
    assert reference_preview.status_code == 200
    assert reference_preview.json()["valid"] is False


def test_joined_validation_routes_support_the_complete_local_workflow(tmp_path):
    database_path = tmp_path / "application.sqlite3"
    connection = connect_database(database_path)
    try:
        initialise_database(connection)
        pd_id = import_document(
            connection,
            extract_document(
                FIXTURES / "10108-01 Alternate Dispute Resolution Specialist - TW9.docx"
            ),
        )
    finally:
        connection.close()

    settings = WebSettings(
        database_path=database_path,
        model_name=DEFAULT_MODEL_NAME,
        environment="test",
    )
    with TestClient(create_app(settings)) as client:
        records = client.get("/api/validation/pds")
        detail = client.get(f"/api/validation/pds/{pd_id}")
        draft = detail.json()["draft"]
        draft["pd_record"]["role_title"] = "Reviewed role title"
        save = client.put(
            f"/api/validation/pds/{pd_id}/draft",
            json={"draft": draft, "section_statuses": {}, "edited_paths": ["role_details"]},
        )
        confirm = client.post(
            f"/api/validation/pds/{pd_id}/confirm",
            json={"draft": draft, "section_statuses": {}, "edited_paths": ["role_details"]},
        )
        export = client.get(f"/api/validation/pds/{pd_id}/export")

    assert records.status_code == 200
    assert records.json()[0]["id"] == pd_id
    assert detail.status_code == 200
    assert save.json() == {"ok": True}
    assert confirm.json() == {"ok": True, "errors": []}
    assert export.status_code == 200
    assert export.json()["pd_record"]["role_title"] == "Reviewed role title"


def test_version_and_core_data_routes(tmp_path):
    with client_for(tmp_path) as client:
        version = client.get("/api/version")
        classifications = client.get("/api/classifications")
        pds = client.get("/api/pds?q=payroll")

    assert version.status_code == 200
    assert version.json()["model"] == DEFAULT_MODEL_NAME
    assert classifications.status_code == 200
    assert "rows" in classifications.json()
    assert pds.status_code == 200
    assert pds.json() == []


def test_invalid_career_cursor_retains_existing_api_contract(tmp_path):
    with client_for(tmp_path) as client:
        response = client.get("/api/career-explorer/neighbours?role_id=1&cursor=nope")

    assert response.status_code == 400
    assert response.json() == {"error": "cursor must be an integer"}


def test_railway_runtime_settings_use_injected_host_and_port(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "staging")
    monkeypatch.setenv("PORT", "4321")
    monkeypatch.setenv("PD_MANAGEMENT_DEPLOYMENT_PROFILE", "explorer-demo")
    monkeypatch.setenv("PD_MANAGEMENT_REQUIRE_DATA", "true")

    settings = web_settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 4321
    assert settings.deployment_profile == "explorer-demo"
    assert settings.require_data is True


def test_explorer_demo_profile_hides_administration_and_writes(tmp_path):
    settings = WebSettings(
        database_path=tmp_path / "application.sqlite3",
        model_name=DEFAULT_MODEL_NAME,
        environment="test",
        deployment_profile="explorer-demo",
    )
    with TestClient(create_app(settings)) as client:
        home = client.get("/", follow_redirects=False)
        admin = client.get("/admin/classifications")
        write = client.put("/api/classifications", json={"rows": []})
        live = client.get("/health/live")

    assert home.status_code == 302
    assert home.headers["location"] == "/career-explorer"
    assert admin.status_code == 404
    assert write.status_code == 404
    assert live.status_code == 200


def test_admin_poc_readonly_requires_credentials_at_startup(tmp_path):
    settings = WebSettings(
        database_path=tmp_path / "application.sqlite3",
        model_name=DEFAULT_MODEL_NAME,
        deployment_profile="admin-poc-readonly",
    )

    try:
        create_app(settings)
    except ValueError as exc:
        assert "PD_MANAGEMENT_ADMIN_USERNAME" in str(exc)
    else:
        raise AssertionError("Admin PoC started without access credentials")


def test_admin_poc_readonly_challenges_admin_and_blocks_writes(tmp_path):
    settings = WebSettings(
        database_path=tmp_path / "application.sqlite3",
        model_name=DEFAULT_MODEL_NAME,
        environment="test",
        deployment_profile="admin-poc-readonly",
        admin_username="reviewer",
        admin_password="not-a-real-secret",
    )
    with TestClient(create_app(settings)) as client:
        unauthenticated = client.get("/")
        wrong = client.get("/", auth=("reviewer", "wrong"))
        authenticated = client.get("/", auth=("reviewer", "not-a-real-secret"))
        admin = client.get(
            "/admin/classifications", auth=("reviewer", "not-a-real-secret")
        )
        validation = client.get(
            "/validation", auth=("reviewer", "not-a-real-secret")
        )
        validation_records = client.get(
            "/api/validation/pds", auth=("reviewer", "not-a-real-secret")
        )
        reference_workbook = client.get(
            "/api/reference-data-workbook", auth=("reviewer", "not-a-real-secret")
        )
        semantic_search = client.get(
            "/api/search?query=payroll", auth=("reviewer", "not-a-real-secret")
        )
        write = client.put(
            "/api/classifications",
            auth=("reviewer", "not-a-real-secret"),
            json={"rows": []},
        )
        validation_write = client.put(
            "/api/validation/pds/1/draft",
            auth=("reviewer", "not-a-real-secret"),
            json={"draft": {}},
        )
        reference_upload = client.post(
            "/api/reference-data-workbook/preview",
            auth=("reviewer", "not-a-real-secret"),
            json={
                "filename": "reference.xlsx",
                "content_base64": base64.b64encode(reference_workbook.content).decode(),
            },
        )
        reference_apply = client.post(
            "/api/reference-data-workbook/apply",
            auth=("reviewer", "not-a-real-secret"),
            json={"filename": "reference.xlsx", "content_base64": "UEs="},
        )
        public_health = client.get("/health/live")

    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"].startswith("Basic ")
    assert wrong.status_code == 401
    assert authenticated.status_code == 200
    assert "Hosted read-only proof of concept" in authenticated.text
    assert "Upload disabled" in authenticated.text
    assert "Validate workbook" in authenticated.text
    assert "Apply disabled on Railway" in authenticated.text
    assert admin.status_code == 200
    assert "Save disabled" in admin.text
    assert validation.status_code == 200
    assert "editing and validation are disabled" in validation.text
    assert validation_records.status_code == 200
    assert validation_records.json() == []
    assert reference_workbook.status_code == 200
    assert reference_workbook.content.startswith(b"PK")
    assert authenticated.headers["cache-control"] == "no-store"
    assert authenticated.headers["vary"] == "Authorization"
    assert semantic_search.status_code == 503
    assert semantic_search.json() == {
        "error": "Semantic search is disabled in the hosted PoC"
    }
    assert write.status_code == 405
    assert write.json() == {"error": "Hosted administration is read-only"}
    assert validation_write.status_code == 405
    assert validation_write.json() == {"error": "Hosted administration is read-only"}
    assert reference_upload.status_code == 200
    assert reference_upload.json()["valid"] is False
    assert reference_apply.status_code == 405
    assert reference_apply.json() == {"error": "Hosted administration is read-only"}
    assert public_health.status_code == 200


def test_require_data_fails_readiness_for_empty_database(tmp_path):
    settings = WebSettings(
        database_path=tmp_path / "application.sqlite3",
        model_name=DEFAULT_MODEL_NAME,
        environment="test",
        deployment_profile="explorer-demo",
        require_data=True,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_unknown_deployment_profile_is_rejected(tmp_path):
    settings = WebSettings(
        database_path=tmp_path / "application.sqlite3",
        model_name=DEFAULT_MODEL_NAME,
        deployment_profile="public-everything",
    )

    try:
        create_app(settings)
    except ValueError as exc:
        assert "PD_MANAGEMENT_DEPLOYMENT_PROFILE" in str(exc)
    else:
        raise AssertionError("unsafe unknown deployment profile was accepted")
