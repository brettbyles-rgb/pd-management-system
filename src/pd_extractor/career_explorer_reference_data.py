from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT


FAMILY_TIERS_PATH = (
    PROJECT_ROOT / "data" / "reference" / "career_pathways_family_tiers_provisional.json"
)


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _level(value: object) -> int:
    return max(0, int(round(_float(value))))


def _role_title(title: object, filename: object, pd_number: object) -> str:
    value = str(title or "").strip()
    if value:
        return value
    value = Path(str(filename or "")).stem
    number = re.escape(str(pd_number or "").strip())
    if number:
        value = re.sub(rf"^{number}\s*[-–—]?\s*", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+-\s+(?:TWL?\d+|TM\d+|PSSE.*|SEO|CEO)\s*$", "", value).strip()


def _family_path(
    code: str,
    nodes: dict[str, dict[str, str]],
) -> tuple[str, str, str]:
    family = subfamily = specialisation = ""
    seen: set[str] = set()
    current = code
    while current and current not in seen:
        seen.add(current)
        node = nodes.get(current)
        if not node:
            break
        level = node["level"].lower()
        if "job family" in level:
            family = node["name"]
        elif "sub" in level:
            subfamily = node["name"]
        elif "special" in level:
            specialisation = node["name"]
        parent = node["parent_code"]
        if parent == current:
            break
        current = parent
    return family, subfamily, specialisation


def _family_model(connection: sqlite3.Connection) -> tuple[list[str], list[list[int]]]:
    reference = json.loads(FAMILY_TIERS_PATH.read_text(encoding="utf-8"))
    reference_families = [str(value) for value in reference["families"]]
    reference_tiers = reference["tiers"]
    tier_by_pair = {
        (left, right): int(reference_tiers[i][j])
        for i, left in enumerate(reference_families)
        for j, right in enumerate(reference_families)
    }
    live_families = [
        str(row[0])
        for row in connection.execute(
            """SELECT name FROM job_family_nodes
               WHERE LOWER(level) = 'job family'
               ORDER BY sequence, name"""
        )
    ]
    families = live_families or reference_families
    if "UNMAPPED" not in families:
        families.append("UNMAPPED")
    tiers = [
        [
            -1 if left == right else tier_by_pair.get((left, right), 2)
            for right in families
        ]
        for left in families
    ]
    return families, tiers


def build_reference_payloads(connection: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project the unified database into the reference prototype's two data contracts."""
    node_rows = connection.execute(
        "SELECT code, name, level, parent_code FROM job_family_nodes"
    ).fetchall()
    nodes = {
        str(row["code"]): {
            "name": str(row["name"] or ""),
            "level": str(row["level"] or ""),
            "parent_code": str(row["parent_code"] or ""),
        }
        for row in node_rows
    }
    primary_mappings = {
        str(row["role_id"]): str(row["mapping_code"] or "")
        for row in connection.execute(
            """WITH ranked AS (
                   SELECT m.*,
                          ROW_NUMBER() OVER (
                              PARTITION BY role_id
                              ORDER BY CASE WHEN LOWER(COALESCE(mapping_validated,''))='yes'
                                            THEN 0 ELSE 1 END,
                                       COALESCE(framework_code_valid,0) DESC,
                                       mapping_rank,
                                       mapping_code
                          ) AS selection_order
                   FROM role_job_family_mappings m
                   WHERE mapping_rank = 1
               )
               SELECT role_id, mapping_code FROM ranked WHERE selection_order = 1"""
        )
    }
    role_rows = connection.execute(
        """SELECT pd.role_id, pd.role_title, pd.position_description_no,
                  pd.source_filename, pd.classification_grade_band,
                  COALESCE(cr.abbreviation,'') AS abbreviation,
                  COALESCE(cr.display_label,'') AS display_label,
                  COALESCE(cr.seniority_order,0) AS seniority_order
           FROM position_descriptions pd
           LEFT JOIN classification_references cr
                  ON cr.raw_label = pd.classification_grade_band
           WHERE pd.role_id IS NOT NULL AND pd.role_id <> ''
           ORDER BY LOWER(pd.role_title), pd.role_id"""
    ).fetchall()

    role_ids = [str(row["role_id"]) for row in role_rows]
    role_index = {role_id: index for index, role_id in enumerate(role_ids)}
    total_roles = len(role_ids)

    activity_rows = connection.execute(
        """SELECT a.activity_id, a.canonical_match_label, a.canonical_plain_label,
                  a.cluster_id, COALESCE(s.share,0) AS share
           FROM activities a
           LEFT JOIN activity_statistics s ON s.activity_id = a.activity_id
           ORDER BY a.activity_id"""
    ).fetchall()
    activity_to_cluster: dict[str, int] = {}
    cluster_labels: dict[int, tuple[str, str]] = {}
    vocabulary: dict[str, dict[str, Any]] = {}
    for row in activity_rows:
        activity_id = str(row["activity_id"])
        cluster_text = str(row["cluster_id"] or "").strip()
        if cluster_text:
            cluster_id = int(cluster_text)
            activity_to_cluster[activity_id] = cluster_id
            cluster_labels.setdefault(
                cluster_id,
                (
                    str(row["canonical_plain_label"] or ""),
                    str(row["canonical_match_label"] or ""),
                ),
            )
        vocabulary[activity_id] = {
            "m": str(row["canonical_match_label"] or ""),
            "p": str(row["canonical_plain_label"] or ""),
            "share": round(_float(row["share"]), 4),
        }

    role_activity_ids: dict[str, list[str]] = defaultdict(list)
    role_clusters: dict[str, list[int]] = defaultdict(list)
    cluster_roles: dict[int, set[str]] = defaultdict(set)
    for row in connection.execute(
        "SELECT role_id, activity_id FROM role_activities ORDER BY role_id, activity_rank"
    ):
        role_id = str(row["role_id"])
        activity_id = str(row["activity_id"])
        if activity_id not in role_activity_ids[role_id]:
            role_activity_ids[role_id].append(activity_id)
        cluster_id = activity_to_cluster.get(activity_id)
        if cluster_id is not None and cluster_id not in role_clusters[role_id]:
            role_clusters[role_id].append(cluster_id)
            cluster_roles[cluster_id].add(role_id)

    capability_names = [
        str(row[0])
        for row in connection.execute(
            """SELECT capability_name FROM capabilities
               WHERE capability_name IS NOT NULL AND capability_name <> ''
               GROUP BY capability_name ORDER BY MIN(capability_id)"""
        )
    ]
    capability_index = {name: index for index, name in enumerate(capability_names)}
    all_caps: dict[str, dict[str, int]] = defaultdict(dict)
    focus_caps: dict[str, dict[str, int]] = defaultdict(dict)
    cap_roles: dict[str, set[str]] = defaultdict(set)
    for row in connection.execute(
        """SELECT role_id, capability_name, capability_type, normalized_level
           FROM role_capabilities
           WHERE capability_name IS NOT NULL AND capability_name <> ''
             AND normalized_level IS NOT NULL
           ORDER BY role_id, sequence"""
    ):
        role_id = str(row["role_id"])
        name = str(row["capability_name"])
        level = _level(row["normalized_level"])
        if not level:
            continue
        all_caps[role_id][name] = max(level, all_caps[role_id].get(name, 0))
        if "focus" in str(row["capability_type"] or "").lower():
            focus_caps[role_id][name] = max(level, focus_caps[role_id].get(name, 0))
        cap_roles[name].add(role_id)

    families, tiers = _family_model(connection)
    family_index = {name: index for index, name in enumerate(families)}
    role_meta: dict[str, dict[str, Any]] = {}
    route_roles: list[dict[str, Any]] = []
    constellation_roles: list[dict[str, Any]] = []
    for row in role_rows:
        role_id = str(row["role_id"])
        family, subfamily, specialisation = _family_path(
            primary_mappings.get(role_id, ""), nodes
        )
        family = family or "UNMAPPED"
        abbreviation = str(row["abbreviation"] or "")
        display = str(row["display_label"] or row["classification_grade_band"] or "")
        raw = str(row["classification_grade_band"] or "")
        order = _float(row["seniority_order"])
        meta = {
            "title": _role_title(
                row["role_title"], row["source_filename"], row["position_description_no"]
            ),
            "family": family,
            "subfamily": subfamily,
            "specialisation": specialisation,
            "abbreviation": abbreviation or raw,
            "display": display or raw,
            "order": order,
        }
        role_meta[role_id] = meta
        route_roles.append({
            "t": meta["title"],
            "c": meta["abbreviation"],
            "cl": meta["display"],
            "a": order,
            "f": family if family != "UNMAPPED" else "",
            "s": subfamily,
            "fc": [[name, level] for name, level in focus_caps[role_id].items()],
            "ac": [[name, level] for name, level in all_caps[role_id].items()],
            "act": role_activity_ids[role_id],
        })
        constellation_roles.append({
            "t": meta["title"],
            "f": family_index[family],
            "sf": subfamily,
            "sp": specialisation,
            "g": meta["display"],
            "ga": meta["abbreviation"],
            "go": order,
            "p": role_clusters[role_id],
            "m": [],
            "cp": [
                [capability_index[name], level]
                for name, level in focus_caps[role_id].items()
                if name in capability_index
            ],
        })

    edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute(
        """SELECT role_id, neighbour_role_id, score, readiness_rdy,
                  grade_step_dg, work_similarity_cr, same_subfamily_ssub
           FROM role_neighbours
           ORDER BY role_id, CAST(neighbour_rank AS INTEGER)"""
    ):
        source = role_index.get(str(row["role_id"]))
        target = role_index.get(str(row["neighbour_role_id"]))
        if source is None or target is None:
            continue
        edges[str(source)].append({
            "to": target,
            "w": round(_float(row["score"]), 3),
            "rdy": round(_float(row["readiness_rdy"]), 3),
            "dg": _float(row["grade_step_dg"]),
            "cr": round(_float(row["work_similarity_cr"]), 3),
            "ssub": str(row["same_subfamily_ssub"] or "").lower() == "true",
        })

    cluster_payload = {
        str(cluster_id): {
            "plain": labels[0],
            "match": labels[1],
            "w": round(
                max(0.25, math.log(total_roles / max(1, len(cluster_roles[cluster_id])))),
                3,
            ),
        }
        for cluster_id, labels in sorted(cluster_labels.items())
    }
    adjacency = {
        f"{left}|{right}": tiers[i][j]
        for i, left in enumerate(families)
        for j, right in enumerate(families)
        if left != right
    }
    capability_rarity = {
        name: round(1 - (len(cap_roles[name]) / total_roles), 3)
        for name in capability_names
    }
    route_payload = {
        "r": route_roles,
        "e": dict(edges),
        "idf": capability_rarity,
        "vocab": vocabulary,
        "adj": adjacency,
    }
    constellation_payload = {
        "families": families,
        "tiers": tiers,
        "clusters": cluster_payload,
        "roles": constellation_roles,
        "caps": capability_names,
    }
    return route_payload, constellation_payload
