# Constellation algorithm implementation

## Status

Algorithm version `constellation-provisional-0.1.0` implements the supplied specification and untuned placeholder configuration. It is installed alongside the existing provisional neighbour graph; it does not replace `role_neighbours` until all maintained inputs pass readiness validation.

## Implemented decisions

- Straight activity overlap: shared count divided by the smaller role's activity count.
- Rarity overlap: rarity-weighted Jaccard.
- Component weights: activity plain 0.30, activity rarity 0.30, occupational 0.20, adjacency 0.10 and grade 0.10.
- Relatedness floor: 0.12, inclusive.
- Occupational ladder: 0.34 family base, 0.33 subfamily bonus and 0.33 specialisation bonus, capped at 1.0.
- Family tiers: 0 maps to 1.0, 1 maps to 0.5 and 2 maps to 0.0. Tier 2 is not a hard gate.
- Grade direction: positive is a move to a more senior rung. Default permits same grade through three rungs up. The alternate pool permits two rungs down with the 0.6 factor.
- Capabilities are excluded.
- Ranking is deterministic by descending score and then stable role ID.
- Paging replaces the visible fan, caps it at three, wraps after exhaustion and removes anchored nodes from the live pool.

## Database objects

- `constellation_algorithm_versions`: version and publication status.
- `constellation_parameters`: every numeric and behavioural parameter.
- `constellation_grade_rungs`: provisional classification-to-rung mapping.
- `constellation_family_adjacency`: maintained 32x32 tier matrix.
- `constellation_role_features`: exact feature projection used for a release.
- `constellation_candidate_scores`: every directed role pair, component, contribution, exclusion, score and rank.
- `constellation_neighbours_default`: eligible level-or-up ranked pool.
- `constellation_neighbours_allow_down`: eligible ranked pool when downward roles are permitted.

The scorer stores all directed candidate pairs rather than only the first 25. This supports the finite `of N` pool, deep paging and complete audit reconstruction.

## Publication gate

`python -m pd_extractor.pathways.constellation validate` reports maintained-data readiness. `build` refuses to publish if activity coverage, primary family mapping, grade-rung coverage or any matrix cell is missing. No missing input is silently converted into a zero similarity.

When the data is ready, run:

```powershell
python -m pd_extractor.pathways.constellation build
```

The existing `role_neighbours` table remains the active rollback version until the new graph is reviewed and explicitly adopted.
