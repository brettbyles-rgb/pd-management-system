# GitHub, Railway and Supabase migration plan

**Status:** In progress  
**Target:** Controlled non-production integration environment  
**Local baseline:** Retained until cloud reconciliation and recovery tests pass

## Platform roles

| Platform | Initial role | Boundary |
| --- | --- | --- |
| GitHub | Private source control and deployment source | No databases, uploaded PDs, backups, logs or secrets |
| Railway | Stateless application runtime for a controlled test/demo | Use the `explorer-demo` profile until authentication and authorisation exist |
| Supabase | Sydney-region PostgreSQL target | Database migration is required; the current SQLite file cannot simply be attached |
| Local workstation | Known-good application and data rollback | Remains authoritative during migration verification |

## Implemented deployment safeguards

- Railway's injected `PORT` is recognised automatically.
- Railway defaults to listening on `0.0.0.0`; local execution remains loopback-only.
- `PD_MANAGEMENT_DEPLOYMENT_PROFILE=explorer-demo` exposes only the Explorer and operational health/version endpoints.
- Non-GET requests and administration routes return `404` in the demo profile.
- `PD_MANAGEMENT_REQUIRE_DATA=true` prevents readiness from passing when the database is empty or lacks pathway data.
- The container runs as a non-root user.
- The Docker build excludes databases, documents, generated output, backups, logs, local environments and `.env` files.
- No cloud credentials or connection strings are committed.

These controls reduce accidental exposure. They are not a replacement for Microsoft Entra ID, application roles, formal approval or production security controls.

## Railway staging variables

Do not configure these until a safe database target is available:

```text
PD_MANAGEMENT_ENVIRONMENT=staging
PD_MANAGEMENT_DEPLOYMENT_PROFILE=explorer-demo
PD_MANAGEMENT_REQUIRE_DATA=true
PD_MANAGEMENT_LOG_LEVEL=INFO
```

Railway supplies `PORT`. No public domain should be enabled while readiness fails or while the full unauthenticated profile is selected.

## Migration stages

### 1. Deployment foundation — current

- Reproducible Docker build.
- Railway service configuration and health check.
- Explicit public demo surface.
- Environment-driven runtime settings.

### 2. PostgreSQL compatibility — in progress

- PostgreSQL driver and a shared connection boundary are now available for the
  read-only Explorer deployment profile.
- Versioned PostgreSQL migrations and an explicit migration runner have been added.
- The Explorer path no longer depends on SQLite-only placeholders or schema inspection.
- Preserve SQLite-backed tests during the transition.
- Add PostgreSQL integration tests against a disposable schema.

The PostgreSQL path is intentionally refused when the `full` deployment profile is
selected. Validation, mapping, imports and administration remain SQLite-only until
their writes, file storage, audit and authorisation controls are migrated.

### Controlled migration commands

Keep the connection URL in the current process environment; never put it in a
command, source file or chat message. After setting `PD_MANAGEMENT_DATABASE_URL`:

```powershell
python scripts/apply_postgres_migrations.py
python scripts/copy_explorer_to_postgres.py --source data/generated/pd_management_unified.sqlite3
python scripts/copy_explorer_to_postgres.py --source data/generated/pd_management_unified.sqlite3 --apply
```

The first copy command is inspection-only. The apply command refuses to overwrite
non-empty target tables and reconciles every copied table count before committing.

### 3. Controlled data copy

- Confirm the Supabase project uses the specific Oceania (Sydney) region.
- Create a least-privilege application database role.
- Enforce and verify TLS.
- Apply schema migrations separately from application startup.
- Copy an approved snapshot of the current unified data.
- Reconcile table counts, stable role IDs, relationships, mapping outputs and Explorer payload hashes.

### 4. Read-only cloud verification

- Connect Railway to Supabase using a protected Railway secret.
- Keep the Explorer-only profile enabled.
- Verify readiness, performance, logs and failure behaviour.
- Keep the local application and database unchanged as rollback.

### 5. Identity and controlled writes

- Integrate Microsoft Entra ID.
- Define viewer, validator, mapper and reference-administrator application roles.
- Enforce authorisation in backend routes, not only in navigation.
- Add durable audit events for governed changes.
- Only then enable validation, mapping, classification and import writes.

### 6. Files, recovery and scale

- Move uploaded source documents from local disk to governed object storage.
- Back up database and object storage independently.
- Test restore and rollback procedures.
- Separate expensive embedding/pathway generation from web requests into controlled worker jobs.
- Load-test representative journeys and concurrency before any broader rollout.

## Current hard blockers to a full cloud deployment

1. Write workflows still import and depend directly on Python's `sqlite3` API.
2. Source documents, workbook imports and classification backups are written to local paths.
3. Validation still runs through a separate legacy HTTP server.
4. The full application has no authentication or route-level permissions.
5. The Supabase project connection, region, roles, TLS and backup settings have not yet been verified from the application.
6. Railway's current Asia-Pacific application region is outside Australia, so its acceptability for any TAFE production workload must not be assumed.

## Cutover rule

Do not delete, replace or overwrite the local unified database during these stages. Cloud data begins as a copy and becomes authoritative only after explicit reconciliation, recovery testing and organisational approval.
