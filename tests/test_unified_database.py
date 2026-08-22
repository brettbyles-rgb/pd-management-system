from __future__ import annotations

import sqlite3
from pathlib import Path

from pd_extractor.intelligence_app import (
    career_explorer_neighbours,
    career_explorer_payload,
)


ROOT = Path(__file__).resolve().parents[1]
PD_SOURCE = ROOT / "output" / "pd-management-bulk-fixed.sqlite3"
UNIFIED = ROOT / "data" / "generated" / "pd_management_unified.sqlite3"


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_unified_database_preserves_every_operational_table_and_row() -> None:
    source = sqlite3.connect(PD_SOURCE)
    unified = sqlite3.connect(UNIFIED)
    try:
        for table in _tables(source):
            assert table in _tables(unified)
            source_count = source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            unified_count = unified.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            assert unified_count == source_count
    finally:
        source.close()
        unified.close()


def test_unified_database_has_stable_identity_and_complete_pathway_outputs() -> None:
    connection = sqlite3.connect(UNIFIED)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT COUNT(*) FROM position_descriptions "
            "WHERE role_id IS NULL OR role_id = ''"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(DISTINCT role_id) FROM position_descriptions"
        ).fetchone()[0] == 1171
        expected = {
            "roles": 1171,
            "role_capabilities": 20891,
            "role_activities": 13936,
            "essential_requirements": 4689,
            "activity_statistics": 1256,
            "activity_rarity": 13936,
            "role_capability_profiles": 20891,
            "role_neighbours": 29275,
        }
        for dataset, count in expected.items():
            assert connection.execute(
                f'SELECT COUNT(*) FROM "{dataset}"'
            ).fetchone()[0] == count
    finally:
        connection.close()


def test_unified_neighbour_scores_are_reconstructable() -> None:
    connection = sqlite3.connect(UNIFIED)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM role_neighbours WHERE "
            "ABS(CAST(score AS REAL) - (CAST(readiness_contribution AS REAL) + "
            "CAST(activity_contribution AS REAL) + CAST(subfamily_contribution AS REAL) + "
            "CAST(classification_contribution AS REAL))) > 0.000002"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_existing_career_explorer_payload_is_unique_and_uses_stable_ids() -> None:
    connection = sqlite3.connect(UNIFIED)
    connection.row_factory = sqlite3.Row
    try:
        payload = career_explorer_payload(connection)
        assert payload["summary"]["role_count"] == 1171
        assert len({row["id"] for row in payload["roles"]}) == 1171
        assert len({row["role_id"] for row in payload["roles"]}) == 1171
        assert sum(bool(row["purpose"]) for row in payload["roles"]) == 1166
    finally:
        connection.close()


def test_career_explorer_neighbour_fan_pages_and_excludes_anchors() -> None:
    connection = sqlite3.connect(UNIFIED)
    connection.row_factory = sqlite3.Row
    try:
        source_role_id = connection.execute(
            "SELECT role_id FROM role_neighbours ORDER BY role_id LIMIT 1"
        ).fetchone()[0]
        first = career_explorer_neighbours(connection, source_role_id)
        assert len(first["items"]) == 3
        assert first["counter"] == f"1\u20133 of {first['total']}"
        assert first["algorithm"]["provisional"] is True
        assert first["algorithm"]["graph_source"] == "role_neighbours"

        second = career_explorer_neighbours(
            connection,
            source_role_id,
            cursor=first["next_cursor"],
        )
        assert {row["role_id"] for row in first["items"]}.isdisjoint(
            row["role_id"] for row in second["items"]
        )

        anchored_role_id = first["items"][0]["role_id"]
        after_anchor = career_explorer_neighbours(
            connection,
            source_role_id,
            anchored_role_ids=(anchored_role_id,),
        )
        assert after_anchor["total"] == first["total"] - 1
        assert anchored_role_id not in {row["role_id"] for row in after_anchor["items"]}
    finally:
        connection.close()
