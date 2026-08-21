from __future__ import annotations

import sqlite3

from pd_extractor.pathways.constellation import (
    ALGORITHM_VERSION,
    CandidateScore,
    ConstellationConfig,
    RoleFeatures,
    install_provisional_configuration,
    page_ranked_pool,
    persist_candidate_scores,
    rank_candidates,
    rarity_weighted_overlap,
    score_candidate,
    straight_overlap,
)


CFG = ConstellationConfig()
RARITY = {"a": 0.2, "b": 0.8, "c": 0.5, "d": 0.9}
ADJACENCY = {("F1", "F2"): 1, ("F2", "F1"): 1, ("F1", "F3"): 2}


def role(
    role_id: str,
    *,
    family: str = "F1",
    subfamily: str | None = "SF1",
    specialization: str | None = "SP1",
    rung: int | None = 10,
    activities: tuple[str, ...] = ("a", "b"),
) -> RoleFeatures:
    return RoleFeatures(
        role_id,
        family,
        subfamily,
        specialization,
        rung,
        frozenset(activities),
    )


def test_overlap_formulas_match_specification() -> None:
    left = frozenset(("a", "b"))
    right = frozenset(("b", "c", "d"))
    assert straight_overlap(left, right) == 0.5
    assert abs(rarity_weighted_overlap(left, right, RARITY) - (0.8 / 2.4)) < 1e-12


def test_occupational_ladder_is_cumulative_and_capped() -> None:
    source = role("source")
    family_only = score_candidate(
        source, role("family", subfamily="SF2", specialization="SP2"), RARITY, ADJACENCY
    )
    same_subfamily = score_candidate(
        source, role("subfamily", specialization="SP2"), RARITY, ADJACENCY
    )
    same_specialization = score_candidate(source, role("specialization"), RARITY, ADJACENCY)
    assert family_only.occupational_proximity == 0.34
    assert same_subfamily.occupational_proximity == 0.67
    assert same_specialization.occupational_proximity == 1.0
    assert all(row.family_adjacency == 0 for row in (family_only, same_subfamily, same_specialization))


def test_different_family_uses_adjacency_not_occupational_score() -> None:
    result = score_candidate(
        role("source"), role("candidate", family="F2"), RARITY, ADJACENCY
    )
    assert result.occupational_proximity == 0
    assert result.adjacency_tier == 1
    assert result.family_adjacency == 0.5
    assert result.adjacency_contribution == 0.05


def test_grade_direction_and_downward_toggle_are_directional() -> None:
    source = role("source", rung=10)
    up = score_candidate(source, role("up", rung=9), RARITY, ADJACENCY)
    down = score_candidate(source, role("down", rung=11), RARITY, ADJACENCY)
    too_far_up = score_candidate(source, role("far", rung=6), RARITY, ADJACENCY)
    assert up.grade_delta == 1 and up.grade_proximity == 0.8 and up.eligible_default
    assert down.grade_delta == -1 and abs(down.grade_proximity - 0.48) < 1e-12
    assert not down.eligible_default and down.eligible_allow_down
    assert down.exclusion_reason_default == "downward_move_disabled"
    assert not too_far_up.eligible_default
    assert too_far_up.exclusion_reason_default == "more_than_three_rungs_up"


def test_tier_two_is_zero_not_a_hard_gate() -> None:
    result = score_candidate(
        role("source"), role("candidate", family="F3"), RARITY, ADJACENCY
    )
    assert result.adjacency_tier == 2
    assert result.family_adjacency == 0
    assert result.eligible_default


def test_missing_adjacency_and_grade_are_explicit_exclusions() -> None:
    missing_adjacency = score_candidate(
        role("source"), role("candidate", family="UNKNOWN"), RARITY, ADJACENCY
    )
    missing_grade = score_candidate(
        role("source"), role("candidate2", rung=None), RARITY, ADJACENCY
    )
    assert missing_adjacency.exclusion_reason_default == "missing_adjacency_tier"
    assert missing_grade.exclusion_reason_default == "missing_grade_rung"


def test_floor_is_inclusive() -> None:
    config = ConstellationConfig(
        w_act_plain=0,
        w_act_rare=0,
        w_occ=0,
        w_adj=0,
        w_grade=0.12,
        floor=0.12,
    )
    result = score_candidate(role("source"), role("candidate"), RARITY, ADJACENCY, config)
    assert result.score == 0.12
    assert result.above_floor and result.eligible_default


def test_ranking_is_deterministic_and_keeps_separate_live_pools() -> None:
    source = role("source", rung=10)
    scores = [
        score_candidate(source, role("b", rung=10), RARITY, ADJACENCY),
        score_candidate(source, role("a", rung=10), RARITY, ADJACENCY),
        score_candidate(source, role("down", rung=11), RARITY, ADJACENCY),
    ]
    ranked = {row.candidate_role_id: row for row in rank_candidates(scores)}
    assert ranked["a"].rank_default == 1
    assert ranked["b"].rank_default == 2
    assert ranked["down"].rank_default is None
    assert ranked["down"].rank_allow_down == 3


def test_configuration_and_score_audit_persist_in_sqlite() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    install_provisional_configuration(connection)
    install_provisional_configuration(connection)
    score = rank_candidates(
        [score_candidate(role("source"), role("candidate"), RARITY, ADJACENCY)]
    )[0]
    assert persist_candidate_scores(connection, [score], "test-release") == 1
    row = connection.execute(
        "SELECT score, act_plain_contribution + act_rare_contribution + "
        "occupational_contribution + adjacency_contribution + grade_contribution, "
        "rank_default FROM constellation_candidate_scores"
    ).fetchone()
    assert abs(row[0] - row[1]) < 1e-12
    assert row[2] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM constellation_parameters WHERE algorithm_version = ?",
        (ALGORITHM_VERSION,),
    ).fetchone()[0] == 25
    assert connection.execute("SELECT COUNT(*) FROM constellation_grade_rungs").fetchone()[0] == 23
    connection.close()


def test_paging_replaces_wraps_and_removes_anchored_nodes() -> None:
    ranked = ("a", "b", "c", "d", "e")
    first = page_ranked_pool(ranked)
    second = page_ranked_pool(ranked, first.next_cursor)
    wrapped = page_ranked_pool(ranked, second.next_cursor)
    after_anchor = page_ranked_pool(ranked, anchored_role_ids=("b", "d"), open_slots=2)
    assert first.role_ids == ("a", "b", "c") and first.counter == "1–3 of 5"
    assert second.role_ids == ("d", "e") and second.counter == "4–5 of 5"
    assert wrapped.role_ids == first.role_ids
    assert after_anchor.role_ids == ("a", "c") and after_anchor.counter == "1–2 of 3"


def test_paging_respects_variable_open_slots_and_fan_cap() -> None:
    assert page_ranked_pool(("a", "b"), open_slots=1).role_ids == ("a",)
    try:
        page_ranked_pool(("a",), open_slots=4)
    except ValueError as exc:
        assert "fan cap" in str(exc)
    else:
        raise AssertionError("fan cap must be enforced")
