from pd_extractor.web_app import _safe_exception_summary


def test_exception_summary_redacts_environment_password(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "not-a-real-secret")

    summary = _safe_exception_summary(
        RuntimeError("connection rejected password=not-a-real-secret")
    )

    assert "not-a-real-secret" not in summary
    assert "[redacted]" in summary


def test_exception_summary_redacts_admin_password(monkeypatch):
    monkeypatch.setenv("PD_MANAGEMENT_ADMIN_PASSWORD", "another-fake-secret")

    summary = _safe_exception_summary(RuntimeError("received another-fake-secret"))

    assert "another-fake-secret" not in summary
    assert "[redacted]" in summary


def test_exception_summary_redacts_postgres_url_password():
    summary = _safe_exception_summary(
        RuntimeError("postgresql://application:not-a-real-secret@example.invalid/db failed")
    )

    assert "not-a-real-secret" not in summary
    assert "postgresql://application:[redacted]@example.invalid/db" in summary
