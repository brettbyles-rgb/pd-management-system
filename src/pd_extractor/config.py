from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ENVIRONMENT_VARIABLE = "PD_MANAGEMENT_DATABASE"
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


def web_settings() -> WebSettings:
    from .embeddings import DEFAULT_MODEL_NAME

    return WebSettings(
        database_path=default_database_path(),
        model_name=os.environ.get("PD_MANAGEMENT_MODEL", DEFAULT_MODEL_NAME),
        host=os.environ.get("PD_MANAGEMENT_HOST", "127.0.0.1"),
        port=int(os.environ.get("PD_MANAGEMENT_PORT", "8766")),
        environment=os.environ.get("PD_MANAGEMENT_ENVIRONMENT", "development"),
        log_level=os.environ.get("PD_MANAGEMENT_LOG_LEVEL", "INFO").upper(),
    )


def default_database_path() -> Path:
    """Return the single application database, with an explicit env override."""
    configured = os.environ.get(DATABASE_ENVIRONMENT_VARIABLE)
    return Path(configured).expanduser().resolve() if configured else UNIFIED_DATABASE
