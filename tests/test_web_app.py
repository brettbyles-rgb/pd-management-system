from __future__ import annotations

from fastapi.testclient import TestClient

from pd_extractor.config import WebSettings, web_settings
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
