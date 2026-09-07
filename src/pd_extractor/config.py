from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ENVIRONMENT_VARIABLE = "PD_MANAGEMENT_DATABASE"
DATABASE_URL_ENVIRONMENT_VARIABLE = "PD_MANAGEMENT_DATABASE_URL"
UNIFIED_DATABASE = PROJECT_ROOT / "data" / "generated" / "pd_management_unified.sqlite3"


@dataclass(frozen=True)
class WebSettings:
    """Runtime settings supplied by the host environment, not application code."""

    database_path: Path
    model_name: str
    host: str = "127.0.0.1"
    port: int = 8766
    environment: str = "development"
    log_level: str = "INFO"
    deployment_profile: str = "full"
    require_data: bool = False
    database_url: str | None = field(default=None, repr=False)
    admin_username: str | None = None
    admin_password: str | None = field(default=None, repr=False)


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def web_settings() -> WebSettings:
    from .embeddings import DEFAULT_MODEL_NAME

    return WebSettings(
        database_path=default_database_path(),
        model_name=os.environ.get("PD_MANAGEMENT_MODEL", DEFAULT_MODEL_NAME),
        host=os.environ.get(
            "PD_MANAGEMENT_HOST",
            "0.0.0.0" if os.environ.get("RAILWAY_ENVIRONMENT") else "127.0.0.1",
        ),
        port=int(os.environ.get("PD_MANAGEMENT_PORT") or os.environ.get("PORT") or "8766"),
        environment=os.environ.get("PD_MANAGEMENT_ENVIRONMENT", "development"),
        log_level=os.environ.get("PD_MANAGEMENT_LOG_LEVEL", "INFO").upper(),
        deployment_profile=os.environ.get("PD_MANAGEMENT_DEPLOYMENT_PROFILE", "full").lower(),
        require_data=_environment_flag("PD_MANAGEMENT_REQUIRE_DATA"),
        database_url=os.environ.get(DATABASE_URL_ENVIRONMENT_VARIABLE) or None,
        admin_username=os.environ.get("PD_MANAGEMENT_ADMIN_USERNAME") or None,
        admin_password=os.environ.get("PD_MANAGEMENT_ADMIN_PASSWORD") or None,
    )


def default_database_path() -> Path:
    """Return the single application database, with an explicit env override."""
    configured = os.environ.get(DATABASE_ENVIRONMENT_VARIABLE)
    return Path(configured).expanduser().resolve() if configured else UNIFIED_DATABASE
