from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

from pd_extractor.pathways.build import _match_text, _normalised_level, _stable_role_id


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_stable_role_id_is_deterministic_and_not_an_array_position() -> None:
    first = _stable_role_id(1)
    assert first == _stable_role_id(1)
    assert first != _stable_role_id(2)
    assert len(first) == 36
    assert first != "1"


def test_capability_level_interpretation_preserves_known_scales() -> None:
    assert _normalised_level("Foundational") == 1
    assert _normalised_level("Highly Advanced") == 5
    assert _normalised_level("Level 4 – SINT") == 4
    assert _normalised_level("Level (PBMG)") is None


def test_legacy_matching_repairs_known_encoding_damage() -> None:
    assert _match_text("Stores Attendant â€“ Hairdressing") == _match_text(
        "Stores Attendant – Hairdressing"
    )


def test_generated_release_has_unique_role_ids_and_resolved_relationships() -> None:
    roles = read_csv(ROOT / "data" / "source" / "canonical" / "roles.csv")
    role_ids = {row["role_id"] for row in roles}
    assert len(roles) == 1171
    assert len(role_ids) == len(roles)
    assert "" not in role_ids

    for relative in (
        "role_capabilities.csv",
        "role_activities.csv",
        "role_job_family_mappings.csv",
        "essential_requirements.csv",
    ):
        rows = read_csv(ROOT / "data" / "source" / "canonical" / relative)
        assert all(not row["role_id"] or row["role_id"] in role_ids for row in rows)


def test_generated_graph_uses_stable_ids_and_fixed_neighbour_count() -> None:
    graph = read_csv(ROOT / "data" / "generated" / "pd_neighbour_graph.csv")
    counts = Counter(row["role_id"] for row in graph)
    assert len(counts) == 1171
    assert set(counts.values()) == {25}
    assert all(row["role_id"] and row["neighbour_role_id"] for row in graph)


def test_all_generated_outputs_share_release_metadata() -> None:
    source_release = json.loads(
        (ROOT / "data" / "source" / "canonical" / "source_release.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (ROOT / "data" / "generated" / "manifest.json").read_text(encoding="utf-8")
    )
    validation = json.loads(
        (ROOT / "data" / "qa" / "validation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["source_release"] == source_release["source_release"]
    assert validation["source_release"] == source_release["source_release"]
    assert manifest["build_version"] == source_release["build_version"]
    config = json.loads(
        (ROOT / "data" / "source" / "canonical" / "build_config.json").read_text(
            encoding="utf-8"
        )
    )
    for name in (
        "pd_activity_rarity.csv",
        "pd_capability_profile_ac.csv",
        "pd_neighbour_graph.csv",
        "role_id_crosswalk.csv",
    ):
        rows = read_csv(ROOT / "data" / "generated" / name)
        assert {row["source_release"] for row in rows} == {
            source_release["source_release"]
        }
        assert {row["build_version"] for row in rows} == {
            source_release["build_version"]
        }
        if name != "role_id_crosswalk.csv":
            assert {row["algorithm_version"] for row in rows} == {
                config["algorithm_version"]
            }


def test_sqlite_is_a_complete_auditable_algorithm_snapshot() -> None:
    database = ROOT / "data" / "generated" / "career_pathways.sqlite3"
    connection = sqlite3.connect(database)
    try:
        objects = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        assert {
            "activity_rarity",
            "activity_statistics",
            "role_capability_profiles",
            "role_neighbours",
            "algorithm_parameters",
            "release_files",
            "role_application_payloads",
            "role_purposes",
            "key_accountabilities",
            "dataset_inventory",
            "role_activity_audit",
            "role_capability_audit",
            "role_neighbour_audit",
        } <= objects
        assert connection.execute("SELECT COUNT(*) FROM activity_rarity").fetchone()[0] == 13936
        assert connection.execute("SELECT COUNT(*) FROM role_neighbours").fetchone()[0] == 29275
        assert connection.execute(
            "SELECT COUNT(*) FROM role_neighbours WHERE "
            "ABS(CAST(score AS REAL) - (CAST(readiness_contribution AS REAL) + "
            "CAST(activity_contribution AS REAL) + CAST(subfamily_contribution AS REAL) + "
            "CAST(classification_contribution AS REAL))) > 0.000002"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT value FROM build_metadata WHERE key='algorithm_version'"
        ).fetchone()[0]
    finally:
        connection.close()
