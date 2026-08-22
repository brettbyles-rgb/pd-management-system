# Unified PD Management and Career Pathways database

## Outcome

`data/generated/pd_management_unified.sqlite3` is now the default database for the PD Management System and Career Pathways Explorer. The former databases remain available as rollback sources.

The newer `output/pd-management-bulk-fixed.sqlite3` is the operational foundation. It contains the maintained PD records, extracted content, validation state, capabilities, classifications, job-family imports, activities and embeddings. The versioned Career Pathways snapshot supplies calculated interpretations and recommendation outputs.

## Authority by dataset

| Unified object | Authority | Treatment |
|---|---|---|
| `position_descriptions` | PD Management System | Authoritative role record; extended with permanent `role_id` and `record_status` |
| `pd_sections`, `pd_list_items` | PD Management System | Authoritative purpose, accountabilities and requirements |
| `capability_frameworks`, `capability_definitions`, `pd_capabilities` | PD Management System | Authoritative capability assignments |
| `classification_references` | PD Management System | Authoritative classification reference |
| active `job_family_entries`, `pd_job_family_mappings` | PD Management System | Authoritative current job-family release and ranked mappings |
| `activity_definitions`, `position_description_activities` | PD Management System | Authoritative activity vocabulary and role assignments |
| `capability_level_rules`, `capability_applicability` | Pathway control data | Maintained interpretation and explicit applicability status |
| `activity_statistics`, `activity_rarity` | Pathway build | Generated corpus measures |
| `role_capability_profiles` | Pathway build | Generated numeric feature projection |
| `role_neighbours` | Pathway build | Generated, versioned provisional recommendations |
| `pathway_algorithm_parameters`, pathway/unified metadata | Build process | Exact configuration, lineage and release control |

Compatibility views expose `roles`, `role_capabilities`, `role_activities`, `activities`, `essential_requirements`, `job_family_nodes` and `role_job_family_mappings` without creating a second maintained copy of those facts.

## Identity

`position_descriptions.id` remains the backend's integer primary key. `position_descriptions.role_id` is the stable UUID shared with the Explorer and published outputs. Both identify one role, but only `role_id` is stable across external releases and safe for frontend URLs, graph edges and integrations.

## Build the integration candidate

```powershell
python scripts/build_unified_database.py
```

The builder:

1. Copies the newer PD Management database to a temporary file.
2. Adds and validates the permanent role UUID.
3. Installs pathway control and generated tables.
4. Creates compatibility and audit views.
5. Records source hashes and release versions.
6. Runs integrity, relationship, count and score-reconciliation checks.
7. Atomically publishes `pd_management_unified.sqlite3` only when validation passes.

Validation is written to `data/qa/unified_database_validation.json`.

## Application database setting

Both applications and the supporting administration commands use one central default declared in `pd_extractor.config`:

```powershell
python -m pd_extractor.web_app
python -m pd_extractor.validation_app
```

The existing frontend payload now returns one row for each of the 1,171 stable roles. It retains the integer `id` for existing backend API calls and also publishes `role_id` for pathway data.

The `PD_MANAGEMENT_DATABASE` environment variable and each command's `--database` option remain deliberate test/rollback overrides. SQLite connections enable foreign keys, a five-second busy timeout and WAL journal mode for safer local application reads and writes.

## Refresh pathway calculations

```powershell
python scripts/rebuild_unified_system.py
```

This imports maintained role, classification, job-family and capability data from the unified database, rebuilds the versioned Career Pathways snapshot, and atomically refreshes generated tables in the same unified file. The release fingerprint hashes only maintained input rows plus the activity workbook, not the database file containing the previous generated outputs. Two consecutive rebuilds with unchanged inputs produced the same release `f2fd372bffce0fa9`.

The activity workbook remains a maintained input for activity assignments in this release. Its assignments are also persisted in the unified database; eliminating that remaining external build input should be treated as a separately controlled data-authority change.

## Cutover verification (18 August 2026)

- Disposable backend write test: pass (validation save/confirm, mapping assignment, classification update and transaction rollback).
- SQLite integrity: `ok`; foreign-key issues: zero.
- Explorer payload: 1,171 roles and 1,171 unique stable role IDs; 1,166 populated purposes.
- Generated data: 13,936 role activities, 20,891 capability profiles and 29,275 neighbour edges.
- Rebuild repeatability: unchanged logical input hash `75f02c69faf94d71186581b1b48a7e0ccb2baeb7c39b4fef9136e2e95b2af4b0` and unchanged pathway release across two consecutive rebuilds.
- Regression checks: all 11 pathway/unified test functions passed.

The pre-cutover database is retained at `data/backups/pd_management_unified_pre_cutover_2026-08-18.sqlite3` (SHA-256 `b49d4b5d66e1f4021d175958a1f0f157f8c0ab9d5deb7362b3ccd95f2d9fffa2`).

## Rollback

1. Stop both local applications so no SQLite connection is writing.
2. Set `PD_MANAGEMENT_DATABASE` to the pre-cutover backup above, or start each application with `--database` pointing to it.
3. Keep the live unified file for diagnosis; do not overwrite it.
4. Re-run the smoke checks before resuming edits.

## Cutover stages

Stages 1-5 were completed on 18 August 2026. Retirement is intentionally deferred: retain the former databases read-only until the reconciliation and rollback periods are complete.

SQLite is appropriate for the current local/single-writer prototype. If PD Management becomes a concurrently edited multi-user service, migrate the same logical model to PostgreSQL and place the database behind the backend API.
