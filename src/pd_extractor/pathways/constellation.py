from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from pd_extractor.config import default_database_path


ALGORITHM_VERSION = "constellation-provisional-0.1.0"


@dataclass(frozen=True)
class ConstellationConfig:
    w_act_plain: float = 0.30
    w_act_rare: float = 0.30
    w_occ: float = 0.20
    w_adj: float = 0.10
    w_grade: float = 0.10
    floor: float = 0.12
    family_base: float = 0.34
    subfamily_bonus: float = 0.33
    specialization_bonus: float = 0.33
    adj_t0: float = 1.0
    adj_t1: float = 0.5
    adj_t2: float = 0.0
    grade_same: float = 1.0
    grade_up1: float = 0.8
    grade_up2: float = 0.5
    grade_up3: float = 0.3
    grade_up_max: int = 3
    allow_down_default: bool = False
    grade_down_max: int = 2
    grade_down_factor: float = 0.6

    def adjacency_value(self, tier: int) -> float:
        try:
            return {0: self.adj_t0, 1: self.adj_t1, 2: self.adj_t2}[tier]
        except KeyError as exc:
            raise ValueError(f"unsupported adjacency tier: {tier}") from exc

    def grade_value(self, grade_delta: int) -> float:
        """Return grade proximity; positive delta means candidate is more senior."""
        upward = {
            0: self.grade_same,
            1: self.grade_up1,
            2: self.grade_up2,
            3: self.grade_up3,
        }
        if grade_delta >= 0:
            return upward.get(grade_delta, 0.0)
        return upward.get(abs(grade_delta), 0.0) * self.grade_down_factor


GRADE_RUNGS: tuple[tuple[str, ...], ...] = (
    ("PSSE Band 3",),
    ("PSSE Band 2",),
    ("PSSE Band 1",),
    ("PSSE Band 1 / TCLC 1",),
    ("TAFE Manager Level 6",),
    ("TAFE Manager Level 5",),
    ("TAFE Manager Level 4",),
    ("TAFE Manager Level 3",),
    ("TAFE Manager Level 2",),
    ("Chief Education Officer",),
    ("TAFE Manager Level 1",),
    ("TAFE Worker Level 9", "Senior Education Officer"),
    ("TAFE Manager Level 8",),
    ("Education Officer",),
    ("TAFE Worker Level 8",),
    ("TAFE Worker Level 7",),
    ("TAFE Worker Level 6",),
    ("TAFE Worker Level 5",),
    ("TAFE Worker Level 4",),
    ("TAFE Worker Level 3",),
    ("TAFE Worker Level 2",),
    ("TAFE Worker Level 1",),
)


@dataclass(frozen=True)
class RoleFeatures:
    role_id: str
    family: str | None
    subfamily: str | None
    specialization: str | None
    grade_rung: int | None
    activities: frozenset[str]


@dataclass(frozen=True)
class CandidateScore:
    source_role_id: str
    candidate_role_id: str
    shared_activity_count: int
    activity_union_count: int
    act_plain: float
    act_rare: float
    occupational_proximity: float
    adjacency_tier: int | None
    family_adjacency: float
    grade_delta: int | None
    grade_proximity: float
    act_plain_contribution: float
    act_rare_contribution: float
    occupational_contribution: float
    adjacency_contribution: float
    grade_contribution: float
    score: float
    above_floor: bool
    eligible_default: bool
    eligible_allow_down: bool
    exclusion_reason_default: str | None
    exclusion_reason_allow_down: str | None
    rank_default: int | None = None
    rank_allow_down: int | None = None


@dataclass(frozen=True)
class PoolPage:
    role_ids: tuple[str, ...]
    start: int
    end: int
    total: int
    next_cursor: int

    @property
    def counter(self) -> str:
        return "0 of 0" if self.total == 0 else f"{self.start}–{self.end} of {self.total}"


def page_ranked_pool(
    ranked_role_ids: Sequence[str],
    cursor: int = 0,
    anchored_role_ids: Iterable[str] = (),
    open_slots: int = 3,
) -> PoolPage:
    """Return the next replace-not-accumulate fan page over the live pool."""
    if open_slots < 0 or open_slots > 3:
        raise ValueError("open_slots must be between zero and the fan cap of three")
    anchored = set(anchored_role_ids)
    pool = [role_id for role_id in ranked_role_ids if role_id not in anchored]
    total = len(pool)
    if not total or not open_slots:
        return PoolPage((), 0, 0, total, 0 if not total else cursor % total)
    start_index = cursor % total
    page = tuple(pool[start_index : start_index + open_slots])
    end_index = start_index + len(page)
    next_cursor = 0 if end_index >= total else end_index
    return PoolPage(page, start_index + 1, end_index, total, next_cursor)


def straight_overlap(left: frozenset[str], right: frozenset[str]) -> float:
    smaller = min(len(left), len(right))
    return len(left & right) / smaller if smaller else 0.0


def rarity_weighted_overlap(
    left: frozenset[str], right: frozenset[str], rarity: Mapping[str, float]
) -> float:
    union = left | right
    denominator = sum(float(rarity.get(activity, 0.0)) for activity in union)
    if denominator <= 0:
        return 0.0
    numerator = sum(float(rarity.get(activity, 0.0)) for activity in left & right)
    return numerator / denominator


def _eligibility_reason(
    source: RoleFeatures,
    candidate: RoleFeatures,
    grade_delta: int | None,
    adjacency_tier: int | None,
    above_floor: bool,
    *,
    allow_down: bool,
    config: ConstellationConfig,
) -> str | None:
    if not source.activities or not candidate.activities:
        return "missing_activities"
    if not source.family or not candidate.family:
        return "missing_family"
    if source.family != candidate.family and adjacency_tier is None:
        return "missing_adjacency_tier"
    if grade_delta is None:
        return "missing_grade_rung"
    if grade_delta > config.grade_up_max:
        return "more_than_three_rungs_up"
    if grade_delta < 0 and not allow_down:
        return "downward_move_disabled"
    if grade_delta < -config.grade_down_max:
        return "more_than_two_rungs_down"
    if not above_floor:
        return "below_floor"
    return None


def score_candidate(
    source: RoleFeatures,
    candidate: RoleFeatures,
    rarity: Mapping[str, float],
    adjacency_tiers: Mapping[tuple[str, str], int],
    config: ConstellationConfig = ConstellationConfig(),
) -> CandidateScore:
    if source.role_id == candidate.role_id:
        raise ValueError("a role cannot be its own candidate")

    shared = source.activities & candidate.activities
    union = source.activities | candidate.activities
    act_plain = straight_overlap(source.activities, candidate.activities)
    act_rare = rarity_weighted_overlap(source.activities, candidate.activities, rarity)

    same_family = bool(source.family and source.family == candidate.family)
    if same_family:
        occupational = config.family_base
        if source.subfamily and source.subfamily == candidate.subfamily:
            occupational += config.subfamily_bonus
        if source.specialization and source.specialization == candidate.specialization:
            occupational += config.specialization_bonus
        occupational = min(1.0, occupational)
        adjacency_tier = None
        adjacency = 0.0
    else:
        occupational = 0.0
        adjacency_tier = (
            adjacency_tiers.get((source.family, candidate.family))
            if source.family and candidate.family
            else None
        )
        adjacency = (
            config.adjacency_value(adjacency_tier)
            if adjacency_tier is not None
            else 0.0
        )

    grade_delta = (
        source.grade_rung - candidate.grade_rung
        if source.grade_rung is not None and candidate.grade_rung is not None
        else None
    )
    grade = config.grade_value(grade_delta) if grade_delta is not None else 0.0
    contributions = (
        config.w_act_plain * act_plain,
        config.w_act_rare * act_rare,
        config.w_occ * occupational,
        config.w_adj * adjacency,
        config.w_grade * grade,
    )
    score = sum(contributions)
    above_floor = score >= config.floor
    default_reason = _eligibility_reason(
        source,
        candidate,
        grade_delta,
        adjacency_tier,
        above_floor,
        allow_down=False,
        config=config,
    )
    downward_reason = _eligibility_reason(
        source,
        candidate,
        grade_delta,
        adjacency_tier,
        above_floor,
        allow_down=True,
        config=config,
    )
    return CandidateScore(
        source.role_id,
        candidate.role_id,
        len(shared),
        len(union),
        act_plain,
        act_rare,
        occupational,
        adjacency_tier,
        adjacency,
        grade_delta,
        grade,
        *contributions,
        score,
        above_floor,
        default_reason is None,
        downward_reason is None,
        default_reason,
        downward_reason,
    )


def rank_candidates(scores: Iterable[CandidateScore]) -> list[CandidateScore]:
    rows = list(scores)
    default_order = sorted(
        (row for row in rows if row.eligible_default),
        key=lambda row: (-row.score, row.candidate_role_id),
    )
    downward_order = sorted(
        (row for row in rows if row.eligible_allow_down),
        key=lambda row: (-row.score, row.candidate_role_id),
    )
    default_rank = {row.candidate_role_id: rank for rank, row in enumerate(default_order, 1)}
    downward_rank = {
        row.candidate_role_id: rank for rank, row in enumerate(downward_order, 1)
    }
    return [
        CandidateScore(
            **{
                **asdict(row),
                "rank_default": default_rank.get(row.candidate_role_id),
                "rank_allow_down": downward_rank.get(row.candidate_role_id),
            }
        )
        for row in rows
    ]


SCHEMA = """
CREATE TABLE IF NOT EXISTS constellation_algorithm_versions (
    algorithm_version TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('configured','ready','published','superseded')),
    created_at_utc TEXT NOT NULL,
    specification_name TEXT NOT NULL,
    configuration_name TEXT NOT NULL,
    notes TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS constellation_parameters (
    algorithm_version TEXT NOT NULL REFERENCES constellation_algorithm_versions(algorithm_version),
    parameter_key TEXT NOT NULL,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    PRIMARY KEY (algorithm_version, parameter_key)
);
CREATE TABLE IF NOT EXISTS constellation_grade_rungs (
    algorithm_version TEXT NOT NULL REFERENCES constellation_algorithm_versions(algorithm_version),
    rung_index INTEGER NOT NULL,
    classification_label TEXT NOT NULL,
    is_provisional INTEGER NOT NULL CHECK(is_provisional IN (0,1)),
    PRIMARY KEY (algorithm_version, classification_label)
);
CREATE INDEX IF NOT EXISTS constellation_grade_rungs_index
    ON constellation_grade_rungs(algorithm_version, rung_index);
CREATE TABLE IF NOT EXISTS constellation_family_adjacency (
    algorithm_version TEXT NOT NULL REFERENCES constellation_algorithm_versions(algorithm_version),
    source_family_code TEXT NOT NULL,
    target_family_code TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK(tier IN (0,1,2)),
    rationale TEXT,
    PRIMARY KEY (algorithm_version, source_family_code, target_family_code)
);
CREATE TABLE IF NOT EXISTS constellation_role_features (
    algorithm_version TEXT NOT NULL REFERENCES constellation_algorithm_versions(algorithm_version),
    role_id TEXT NOT NULL,
    family_code TEXT,
    subfamily_code TEXT,
    specialization_code TEXT,
    grade_rung INTEGER,
    activity_count INTEGER NOT NULL,
    validation_status TEXT NOT NULL,
    PRIMARY KEY (algorithm_version, role_id)
);
CREATE TABLE IF NOT EXISTS constellation_candidate_scores (
    algorithm_version TEXT NOT NULL REFERENCES constellation_algorithm_versions(algorithm_version),
    source_release TEXT NOT NULL,
    source_role_id TEXT NOT NULL,
    candidate_role_id TEXT NOT NULL,
    shared_activity_count INTEGER NOT NULL,
    activity_union_count INTEGER NOT NULL,
    act_plain REAL NOT NULL,
    act_rare REAL NOT NULL,
    occupational_proximity REAL NOT NULL,
    adjacency_tier INTEGER,
    family_adjacency REAL NOT NULL,
    grade_delta INTEGER,
    grade_proximity REAL NOT NULL,
    act_plain_contribution REAL NOT NULL,
    act_rare_contribution REAL NOT NULL,
    occupational_contribution REAL NOT NULL,
    adjacency_contribution REAL NOT NULL,
    grade_contribution REAL NOT NULL,
    score REAL NOT NULL,
    above_floor INTEGER NOT NULL CHECK(above_floor IN (0,1)),
    eligible_default INTEGER NOT NULL CHECK(eligible_default IN (0,1)),
    eligible_allow_down INTEGER NOT NULL CHECK(eligible_allow_down IN (0,1)),
    exclusion_reason_default TEXT,
    exclusion_reason_allow_down TEXT,
    rank_default INTEGER,
    rank_allow_down INTEGER,
    PRIMARY KEY (algorithm_version, source_role_id, candidate_role_id)
);
CREATE INDEX IF NOT EXISTS constellation_scores_default_rank
    ON constellation_candidate_scores(algorithm_version, source_role_id, rank_default);
CREATE INDEX IF NOT EXISTS constellation_scores_down_rank
    ON constellation_candidate_scores(algorithm_version, source_role_id, rank_allow_down);
DROP VIEW IF EXISTS constellation_neighbours_default;
CREATE VIEW constellation_neighbours_default AS
SELECT * FROM constellation_candidate_scores
WHERE eligible_default = 1 ORDER BY algorithm_version, source_role_id, rank_default;
DROP VIEW IF EXISTS constellation_neighbours_allow_down;
CREATE VIEW constellation_neighbours_allow_down AS
SELECT * FROM constellation_candidate_scores
WHERE eligible_allow_down = 1 ORDER BY algorithm_version, source_role_id, rank_allow_down;
"""


def install_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def install_provisional_configuration(
    connection: sqlite3.Connection,
    algorithm_version: str = ALGORITHM_VERSION,
    config: ConstellationConfig = ConstellationConfig(),
) -> None:
    install_schema(connection)
    with connection:
        connection.execute(
            "INSERT INTO constellation_algorithm_versions VALUES (?, 'configured', ?, ?, ?, ?) "
            "ON CONFLICT(algorithm_version) DO UPDATE SET "
            "status = excluded.status, created_at_utc = excluded.created_at_utc, "
            "specification_name = excluded.specification_name, "
            "configuration_name = excluded.configuration_name, notes = excluded.notes",
            (
                algorithm_version,
                datetime.now(timezone.utc).isoformat(),
                "constellation-algorithm-spec.md",
                "constellation-placeholder-config.md",
                "Untuned placeholder configuration; current role_neighbours retained until validation and approval.",
            ),
        )
        connection.execute(
            "DELETE FROM constellation_parameters WHERE algorithm_version = ?",
            (algorithm_version,),
        )
        parameters = []
        for key, value in asdict(config).items():
            value_type = "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "number"
            parameters.append((algorithm_version, key.upper(), json.dumps(value), value_type))
        parameters.extend(
            (
                (algorithm_version, "PLAIN_OVERLAP_FORMULA", "shared_count / smaller_activity_count", "text"),
                (algorithm_version, "RARITY_OVERLAP_FORMULA", "sum_rarity_shared / sum_rarity_union", "text"),
                (algorithm_version, "TIER2_TREATMENT", "score_zero_not_hard_gate", "text"),
                (algorithm_version, "CAPABILITIES_INCLUDED", "false", "boolean"),
                (algorithm_version, "PAGE_SIZE", "3", "integer"),
            )
        )
        connection.executemany(
            "INSERT INTO constellation_parameters VALUES (?, ?, ?, ?)", parameters
        )
        connection.execute(
            "DELETE FROM constellation_grade_rungs WHERE algorithm_version = ?",
            (algorithm_version,),
        )
        connection.executemany(
            "INSERT INTO constellation_grade_rungs VALUES (?, ?, ?, 1)",
            [
                (algorithm_version, rung, label)
                for rung, labels in enumerate(GRADE_RUNGS)
                for label in labels
            ],
        )


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (name,)
    ).fetchone() is not None


def validate_database_readiness(
    connection: sqlite3.Connection,
    algorithm_version: str = ALGORITHM_VERSION,
) -> dict[str, object]:
    install_schema(connection)
    roles = connection.execute("SELECT COUNT(*) FROM position_descriptions").fetchone()[0]
    activities = connection.execute(
        "SELECT COUNT(DISTINCT position_description_id) FROM position_description_activities"
    ).fetchone()[0]
    mapped_roles = connection.execute(
        "SELECT COUNT(DISTINCT position_description_id) FROM active_pd_job_family_mappings "
        "WHERE mapping_rank = 1 AND position_description_id IS NOT NULL"
    ).fetchone()[0]
    grade_roles = connection.execute(
        "SELECT COUNT(*) FROM position_descriptions p JOIN constellation_grade_rungs g "
        "ON g.algorithm_version = ? AND g.classification_label = p.classification_grade_band",
        (algorithm_version,),
    ).fetchone()[0]
    family_count = connection.execute(
        "SELECT COUNT(*) FROM job_family_nodes WHERE level = 'Job Family'"
    ).fetchone()[0]
    adjacency_rows = connection.execute(
        "SELECT COUNT(*) FROM constellation_family_adjacency WHERE algorithm_version = ?",
        (algorithm_version,),
    ).fetchone()[0]
    expected_adjacency_rows = family_count * family_count
    missing_grade_labels = [
        {"classification": row[0], "roles": row[1]}
        for row in connection.execute(
            "SELECT p.classification_grade_band, COUNT(*) FROM position_descriptions p "
            "LEFT JOIN constellation_grade_rungs g ON g.algorithm_version = ? "
            "AND g.classification_label = p.classification_grade_band "
            "WHERE g.classification_label IS NULL GROUP BY p.classification_grade_band "
            "ORDER BY COUNT(*) DESC, p.classification_grade_band",
            (algorithm_version,),
        )
    ]
    blockers = []
    if activities != roles:
        blockers.append("activity coverage is incomplete")
    if mapped_roles != roles:
        blockers.append("primary job-family coverage is incomplete")
    if grade_roles != roles:
        blockers.append("classification-rung coverage is incomplete")
    if adjacency_rows != expected_adjacency_rows:
        blockers.append("32x32 family adjacency matrix is incomplete")
    return {
        "status": "ready" if not blockers else "blocked",
        "algorithm_version": algorithm_version,
        "roles": roles,
        "roles_with_activities": activities,
        "roles_with_primary_family_mapping": mapped_roles,
        "roles_with_grade_rung": grade_roles,
        "family_count": family_count,
        "adjacency_rows": adjacency_rows,
        "expected_adjacency_rows": expected_adjacency_rows,
        "missing_grade_labels": missing_grade_labels,
        "blockers": blockers,
    }


def persist_candidate_scores(
    connection: sqlite3.Connection,
    scores: Iterable[CandidateScore],
    source_release: str,
    algorithm_version: str = ALGORITHM_VERSION,
) -> int:
    rows = list(scores)
    fields = tuple(CandidateScore.__dataclass_fields__)
    with connection:
        connection.executemany(
            "INSERT OR REPLACE INTO constellation_candidate_scores VALUES ("
            + ",".join("?" for _ in range(2 + len(fields)))
            + ")",
            [
                (
                    algorithm_version,
                    source_release,
                    *(int(value) if isinstance(value, bool) else value for value in asdict(row).values()),
                )
                for row in rows
            ],
        )
    return len(rows)


def load_role_features(
    connection: sqlite3.Connection,
    algorithm_version: str = ALGORITHM_VERSION,
) -> list[RoleFeatures]:
    grade_by_label = {
        str(row[0]): int(row[1])
        for row in connection.execute(
            "SELECT classification_label, rung_index FROM constellation_grade_rungs "
            "WHERE algorithm_version = ?",
            (algorithm_version,),
        )
    }
    nodes = {
        str(row[0]): {"level": str(row[1]), "parent": row[2]}
        for row in connection.execute(
            "SELECT code, level, parent_code FROM job_family_nodes"
        )
    }

    def taxonomy(code: str | None) -> tuple[str | None, str | None, str | None]:
        family = subfamily = specialization = None
        seen: set[str] = set()
        while code and code not in seen:
            seen.add(code)
            node = nodes.get(code)
            if not node:
                break
            level = node["level"]
            if level == "Job Family":
                family = code
            elif level == "Sub-family":
                subfamily = code
            elif level == "Specialisation":
                specialization = code
            code = str(node["parent"]) if node["parent"] else None
        return family, subfamily, specialization

    primary_mapping = {
        int(row[0]): str(row[1])
        for row in connection.execute(
            "WITH ranked AS (SELECT position_description_id, mapping_code, "
            "ROW_NUMBER() OVER (PARTITION BY position_description_id "
            "ORDER BY mapping_rank, id) AS choice "
            "FROM active_pd_job_family_mappings "
            "WHERE position_description_id IS NOT NULL AND mapping_code IS NOT NULL) "
            "SELECT position_description_id, mapping_code FROM ranked WHERE choice = 1"
        )
    }
    activities: dict[int, set[str]] = {}
    for position_id, activity_id in connection.execute(
        "SELECT position_description_id, activity_id FROM position_description_activities"
    ):
        activities.setdefault(int(position_id), set()).add(str(activity_id))

    features = []
    for position_id, role_id, classification in connection.execute(
        "SELECT id, role_id, classification_grade_band FROM position_descriptions "
        "WHERE record_status = 'active' ORDER BY id"
    ):
        family, subfamily, specialization = taxonomy(primary_mapping.get(int(position_id)))
        features.append(
            RoleFeatures(
                str(role_id),
                family,
                subfamily,
                specialization,
                grade_by_label.get(str(classification)),
                frozenset(activities.get(int(position_id), set())),
            )
        )
    return features


def load_activity_rarity(connection: sqlite3.Connection) -> dict[str, float]:
    return {
        str(row[0]): float(row[1])
        for row in connection.execute(
            "SELECT activity_id, rarity_weight FROM activity_statistics"
        )
    }


def load_adjacency_tiers(
    connection: sqlite3.Connection,
    algorithm_version: str = ALGORITHM_VERSION,
) -> dict[tuple[str, str], int]:
    return {
        (str(row[0]), str(row[1])): int(row[2])
        for row in connection.execute(
            "SELECT source_family_code, target_family_code, tier "
            "FROM constellation_family_adjacency WHERE algorithm_version = ?",
            (algorithm_version,),
        )
    }


def _feature_status(feature: RoleFeatures) -> str:
    missing = []
    if not feature.activities:
        missing.append("activities")
    if not feature.family:
        missing.append("family")
    if feature.grade_rung is None:
        missing.append("grade_rung")
    return "ready" if not missing else "missing_" + "_and_".join(missing)


def build_constellation(
    connection: sqlite3.Connection,
    source_release: str,
    algorithm_version: str = ALGORITHM_VERSION,
    config: ConstellationConfig = ConstellationConfig(),
) -> dict[str, object]:
    readiness = validate_database_readiness(connection, algorithm_version)
    if readiness["status"] != "ready":
        raise ValueError(
            "constellation inputs are incomplete: " + "; ".join(readiness["blockers"])
        )
    features = load_role_features(connection, algorithm_version)
    rarity = load_activity_rarity(connection)
    adjacency = load_adjacency_tiers(connection, algorithm_version)
    with connection:
        connection.execute(
            "DELETE FROM constellation_candidate_scores WHERE algorithm_version = ?",
            (algorithm_version,),
        )
        connection.execute(
            "DELETE FROM constellation_role_features WHERE algorithm_version = ?",
            (algorithm_version,),
        )
        connection.executemany(
            "INSERT INTO constellation_role_features VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    algorithm_version,
                    feature.role_id,
                    feature.family,
                    feature.subfamily,
                    feature.specialization,
                    feature.grade_rung,
                    len(feature.activities),
                    _feature_status(feature),
                )
                for feature in features
            ],
        )

    persisted = 0
    default_edges = 0
    allow_down_edges = 0
    for source in features:
        ranked = rank_candidates(
            score_candidate(source, candidate, rarity, adjacency, config)
            for candidate in features
            if candidate.role_id != source.role_id
        )
        persisted += persist_candidate_scores(
            connection, ranked, source_release, algorithm_version
        )
        default_edges += sum(row.eligible_default for row in ranked)
        allow_down_edges += sum(row.eligible_allow_down for row in ranked)
    with connection:
        connection.execute(
            "UPDATE constellation_algorithm_versions SET status = 'published' "
            "WHERE algorithm_version = ?",
            (algorithm_version,),
        )
    return {
        "status": "published",
        "algorithm_version": algorithm_version,
        "source_release": source_release,
        "roles": len(features),
        "candidate_scores": persisted,
        "default_neighbour_edges": default_edges,
        "allow_down_neighbour_edges": allow_down_edges,
    }


def _configuration_fingerprint(config: ConstellationConfig) -> str:
    payload = json.dumps(
        {"config": asdict(config), "grade_rungs": GRADE_RUNGS},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the versioned Constellation scorer")
    parser.add_argument(
        "command", choices=("install", "validate", "build"), nargs="?", default="validate"
    )
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args(argv)
    connection = sqlite3.connect(args.database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        install_provisional_configuration(connection)
        if args.command == "build":
            source_release_row = connection.execute(
                "SELECT value FROM unified_build_metadata WHERE key = 'pathway_source_release'"
            ).fetchone()
            if not source_release_row:
                raise ValueError("unified pathway source release metadata is missing")
            result = build_constellation(connection, str(source_release_row[0]))
        else:
            result = validate_database_readiness(connection)
        result["configuration_sha256"] = _configuration_fingerprint(ConstellationConfig())
    finally:
        connection.close()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
