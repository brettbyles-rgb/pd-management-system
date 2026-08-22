from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TEMPLATE_PATH = Path(__file__).with_name("templates") / "career_pathways_reference.html"


def _script_json(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_career_explorer(
    route_payload: dict[str, Any],
    constellation_payload: dict[str, Any],
) -> str:
    """Render the accepted reference experience with live unified data."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("__ROUTE_DATA__", _script_json(route_payload))
        .replace("__CONSTELLATION_DATA__", _script_json(constellation_payload))
    )
