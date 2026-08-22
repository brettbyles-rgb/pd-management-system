# Existing-to-canonical field mapping

| Existing source | Existing field | Canonical target | Transformation / control |
|---|---|---|---|
| SQLite `position_descriptions` | `id` | `roles.source_db_id`; role-ID crosswalk | Bootstrap lineage only; never exposed as stable identity |
| SQLite `position_descriptions` | `position_description_no` | `roles.pd_number` | Retained business identifier; missing/duplicates reported |
| SQLite `position_descriptions` | title, classification, source fields | `roles.*` | Direct import with provenance |
| Classification references | raw/display/abbreviation/cohort/order | `classification_aliases.*` | CSV is canonical reference representation |
| Active job-family entries | code/name/level/parent | `job_family_nodes.*` | Direct relational hierarchy import |
| Active role mappings | rank/code/name/validation | `role_job_family_mappings.*` | All ranked alternatives retained; no flattening loss |
| PD capabilities | framework/name/code/type/raw level | `capabilities`, `role_capabilities` | Framework-specific source values retained |
| PD capabilities | raw level | `role_capabilities.normalized_level` | Separate calculated interpretation via level rules |
| Activity workbook `PD ID` | role link | `role_activities.role_id` | Join through database ID crosswalk |
| Activity workbook `Activity ID` and labels | activity definition/link | `activities`, `role_activities` | Vocabulary separated from assignments |
| Legacy capability/graph `pd_id` | 0–1,098 array position | `role_id_crosswalk` | Unique title+classification matches only; ambiguous rows reported |
| Legacy activity rarity `pd_id` | database ID | `role_id_crosswalk` | Requires database ID and title agreement |
| Combined JSON flattened family fields | first mapping only | generated application JSON | Rebuilt from ranked mappings; flattened primary fields remain compatibility views |

## Constellation integration contract

The accepted Career Pathways reference experience is retained in
`templates/career_pathways_reference.html`. On every page render the server
projects the unified database's single 1,171-role universe into the reference
walk and constellation contracts. The former 1,099-role and 939-role embedded
copies are not retained.

The reference's browser candidate function is temporarily retained because its
sequencing, grouping, walk and spawn interactions are coupled to that contract.
Its strict thresholds were calibrated for 240 broad clusters; the live source
contains 698 finer clusters. Strict matches therefore remain first, followed by
a labelled-in-code relaxed pool that still requires shared work and an adjacent
family. This keeps the intended three-role fan and same/more-senior branch
controls functional until the governed Constellation scorer is published.

| Algorithm field | Unified source | Current treatment |
|---|---|---|
| Stable role identity | `position_descriptions.role_id` | UUID maintains one shared role ordering for both reference contracts |
| Role activities | `position_description_activities.activity_id` | Server projects activity assignments to activity and cluster lists; three roles are presently missing assignments |
| Activity rarity | `activity_statistics.share` | Server calculates the cluster weight supplied to the temporary reference scorer |
| Family, sub-family, specialisation | active `pd_job_family_mappings` joined to `job_family_entries` | Deepest populated framework IDs become the occupational feature; incomplete primary mappings remain a publication blocker |
| Framework hierarchy | active `job_family_entries.code`, `.level`, `.parent_code` | Used for the cumulative occupational ladder and guarded against hierarchy cycles |
| Grade rung | `position_descriptions.classification_grade_band` joined to `constellation_grade_rungs.classification_label` | Provisional shared-rung map; unmapped classification labels remain a publication blocker |
| Family adjacency | provisional reference tier matrix | Exact reference behaviour retained until `constellation_family_adjacency` is populated; the empty governed matrix remains a publication blocker |
| Candidate scores | `constellation_candidate_scores` | Becomes authoritative only for an algorithm version whose status is `published` |
| Current UI fallback | reference scorer plus `role_neighbours` for route edges | Temporary compatibility layer; not represented as final tuned recommendations |
| Capabilities | `role_capability_profiles` | Excluded from Constellation scoring; reserved for the future directed-walk readiness gate |

The standalone file remains the precise visual and interaction acceptance
reference. Its role copies are replaced at render time and its direct Anthropic
browser call is disabled; the governed server-side provider boundary remains a
future integration.
