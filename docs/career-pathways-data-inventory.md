# Career Pathways data inventory

| File / dataset | Purpose | Rows / shape | Identifier | Classification | Decision |
|---|---|---:|---|---|---|
| `pd-management-bulk-fixed.sqlite3` / `position_descriptions` | Current role catalogue and extracted PD facts | 1,171 roles | database `id`; PD number is non-unique | Maintained upstream | Import into canonical source tables; retain provenance |
| `activity-assigned-clustered-role-links-revised-high-all.xlsx` / Summary | Workbook build summary | 8 × 2 | n/a | Generated summary | Retain for audit |
| same workbook / Role Activity Links | Role-to-activity relationships | 13,936 data rows × 14 | database `PD ID` + `Activity ID` | Maintained/curated relationship output | Import into `role_activities.csv` |
| same workbook / Role Summary | Per-role activity roll-up | 1,168 data rows × 13 | database `PD ID` | Duplicated summary | Regenerate/retire as authority |
| same workbook / Vocabulary Usage | Activity vocabulary statistics | 1,285 data rows × 15 | `Activity ID` | Mixed reference/calculated | Split activity definitions from generated usage measures |
| same workbook / Role Activity Matrix | Wide role/activity matrix | 1,168 data rows × 1,288 | database `PD ID` | Generated duplicate | Regenerate/retire as authority |
| `classification-references-20260716-145030.csv/json` | Classification aliases and ordering | 69 records | raw classification label | Maintained reference, duplicated formats | Canonical CSV in `data/reference`; JSON retired |
| combined career-pathways JSON | Application bundle of role facts | 1,171 roles | PD number/title only; neither unique | Generated from SQLite | Regenerate with `role_id` and release metadata |
| `pd_activity_rarity.csv` | Per-role activity rarity | 13,001 rows; 1,087 roles | database-like `pd_id` | Calculated, stale/incomplete | Regenerate from canonical role activities |
| `pd_capability_profile_ac.csv` | Flattened numeric capability profile | 19,878 rows; 1,099 roles | positional `pd_id` 0–1,098 | Calculated from older catalogue | Regenerate with stable `role_id`, raw and interpreted levels |
| `pd_neighbour_graph.csv` | Candidate role adjacency | 42,582 rows; 1,099 roles | positional `pd_id` 0–1,098 | Calculated from older catalogue | Regenerate provisionally; final pathway algorithm remains out of scope |

The OneDrive originals remain unmodified. The CSVs under `data/source/onedrive_exports/` are explicitly labelled browser exports and are used only for reconciliation, not as canonical sources.

`walk-algorithm-brief.md` was referenced by the supplied brief but was not present in the OneDrive folder or repository. Its absence is recorded rather than silently substituting an assumed algorithm definition.
