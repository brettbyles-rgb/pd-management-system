from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ENVIRONMENT_VARIABLE = "PD_MANAGEMENT_DATABASE"
UNIFIED_DATABASE = PROJECT_ROOT / "data" / "generated" / "pd_management_unified.sqlite3"


def default_database_path() -> Path:
    """Return the single application database, with an explicit env override."""
    configured = os.environ.get(DATABASE_ENVIRONMENT_VARIABLE)
    return Path(configured).expanduser().resolve() if configured else UNIFIED_DATABASE
