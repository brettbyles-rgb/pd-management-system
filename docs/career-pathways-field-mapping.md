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

The Career Pathways screen reads the searchable role catalogue from the unified
database and obtains each three-role fan from
`GET /api/career-explorer/neighbours`. The browser does not carry its own copy
of the scoring model or source dataset.

| Algorithm field | Unified source | Current treatment |
|---|---|---|
| Stable role identity | `position_descriptions.role_id` | UUID used by the UI, graph and API |
| Role activities | `position_description_activities.activity_id` | Projected into `constellation_role_features`; three roles are presently missing assignments |
| Activity rarity | `activity_statistics.role_share` / `activity_rarity` | Scorer loads the maintained corpus rarity; no browser calculation |
| Family, sub-family, specialisation | active `pd_job_family_mappings` joined to `job_family_entries` | Deepest populated framework IDs become the occupational feature; incomplete primary mappings remain a publication blocker |
| Framework hierarchy | active `job_family_entries.code`, `.level`, `.parent_code` | Used for the cumulative occupational ladder and guarded against hierarchy cycles |
| Grade rung | `position_descriptions.classification_grade_band` joined to `constellation_grade_rungs.classification_label` | Provisional shared-rung map; unmapped classification labels remain a publication blocker |
| Family adjacency | `constellation_family_adjacency` | Intended 32 x 32 maintained matrix; currently empty and therefore a publication blocker |
| Candidate scores | `constellation_candidate_scores` | Becomes authoritative only for an algorithm version whose status is `published` |
| Current UI fallback | `role_neighbours` | Retained `provisional-1.0.0` graph, explicitly labelled provisional by the API and screen |
| Capabilities | `role_capability_profiles` | Excluded from Constellation scoring; reserved for the future directed-walk readiness gate |

The supplied standalone HTML remains a visual and interaction reference only.
Its embedded role copies, walk graph and direct Anthropic API call are not part
of the integrated application.
