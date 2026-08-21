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
