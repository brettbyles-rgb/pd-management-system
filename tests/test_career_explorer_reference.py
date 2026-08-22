from __future__ import annotations

import sqlite3
from pathlib import Path

from pd_extractor.career_explorer_reference_data import build_reference_payloads
from pd_extractor.career_explorer_ui import TEMPLATE_PATH, render_career_explorer


ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "data" / "generated" / "pd_management_unified.sqlite3"


def test_reference_contracts_share_one_complete_role_universe() -> None:
    connection = sqlite3.connect(UNIFIED)
    connection.row_factory = sqlite3.Row
    try:
        route, constellation = build_reference_payloads(connection)
    finally:
        connection.close()

    assert len(route["r"]) == 1171
    assert len(constellation["roles"]) == 1171
    assert [role["t"] for role in route["r"]] == [
        role["t"] for role in constellation["roles"]
    ]
    assert all(role["t"] for role in route["r"])
    assert len(route["e"]) == 1171
    assert len(constellation["families"]) == len(constellation["tiers"])
    assert all(
        len(row) == len(constellation["families"])
        for row in constellation["tiers"]
    )


def test_reference_ui_keeps_every_accepted_surface_and_no_direct_model_call() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    expected_markers = [
        "What do you do now?",
        "Finding your options",
        "Guided walk",
        "Career landscape",
        "SPAWN GRAPH",
        "Shortlist",
        "renderCompare",
        "renderBuild",
        "renderRoute",
    ]
    for marker in expected_markers:
        assert marker in template
    assert "api.anthropic.com" not in template

    rendered = render_career_explorer(
        {"r": [], "e": {}, "idf": {}, "vocab": {}, "adj": {}},
        {"families": [], "tiers": [], "clusters": {}, "roles": [], "caps": []},
    )
    assert "__ROUTE_DATA__" not in rendered
    assert "__CONSTELLATION_DATA__" not in rendered
