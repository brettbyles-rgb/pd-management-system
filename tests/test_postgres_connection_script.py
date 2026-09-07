import argparse
import os
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from postgres_connection import open_postgres_connection  # noqa: E402


class FakePsycopg:
    class Error(Exception):
        pass

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.password_seen = None
        self.keywords = None

    def connect(self, *positional, **keywords):
        self.password_seen = os.environ.get("PGPASSWORD")
        self.keywords = keywords
        if self.fail:
            raise self.Error(f"unsafe diagnostic containing {self.password_seen}")
        return object()


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        database_url_env="PD_MANAGEMENT_DATABASE_URL",
        host="database.example.invalid",
        port=5432,
        user="application",
        database_name="postgres",
        prompt_password=True,
    )


def test_prompted_password_uses_temporary_libpq_environment(monkeypatch):
    monkeypatch.setattr("postgres_connection.getpass.getpass", lambda _: "not-a-real-secret")
    driver = FakePsycopg()

    open_postgres_connection(driver, _args())

    assert driver.password_seen == "not-a-real-secret"
    assert "password" not in driver.keywords
    assert "PGPASSWORD" not in os.environ


def test_connection_error_never_contains_password(monkeypatch):
    monkeypatch.setattr("postgres_connection.getpass.getpass", lambda _: "not-a-real-secret")
    driver = FakePsycopg(fail=True)

    try:
        open_postgres_connection(driver, _args())
    except SystemExit as exc:
        assert "not-a-real-secret" not in str(exc)
        assert "unsafe diagnostic" not in str(exc)
    else:
        raise AssertionError("Connection failure was not reported")
