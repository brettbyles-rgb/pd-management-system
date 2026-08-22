from __future__ import annotations

from fastapi.testclient import TestClient

from pd_extractor.config import WebSettings
from pd_extractor.embeddings import DEFAULT_MODEL_NAME
from pd_extractor.intelligence_app import ADMIN_HTML, HTML_V2
from pd_extractor.web_app import SECURITY_HEADERS, create_app


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

    assert home.status_code == 200
    assert home.text == HTML_V2
    assert admin.status_code == 200
    assert admin.text == ADMIN_HTML


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
