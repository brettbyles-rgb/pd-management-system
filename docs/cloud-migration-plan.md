# GitHub, Railway and Supabase migration plan

**Status:** In progress  
**Target:** Controlled non-production integration environment  
**Local baseline:** Retained until cloud reconciliation and recovery tests pass

## Platform roles

| Platform | Initial role | Boundary |
| --- | --- | --- |
| GitHub | Private source control and deployment source | No databases, uploaded PDs, backups, logs or secrets |
| Railway | Stateless application runtime for a controlled test/demo | Use the `admin-poc-readonly` profile for the joined protected demonstration |
| Supabase | Sydney-region PostgreSQL target | Database migration is required; the current SQLite file cannot simply be attached |
| Local workstation | Known-good application and data rollback | Remains authoritative during migration verification |

## Implemented deployment safeguards

- Railway's injected `PORT` is recognised automatically.
- Railway defaults to listening on `0.0.0.0`; local execution remains loopback-only.
- `PD_MANAGEMENT_DEPLOYMENT_PROFILE=admin-poc-readonly` exposes the public Explorer plus a Basic-auth-protected, read-only administration workspace.
- Non-GET requests are rejected and write controls are visibly disabled in the hosted profile.
- Railway connects to PostgreSQL as the dedicated `pd_management_reader` role rather than the database owner.
- `PD_MANAGEMENT_REQUIRE_DATA=true` prevents readiness from passing when the database is empty or lacks pathway data.
- The container runs as a non-root user.
- The Docker build excludes databases, documents, generated output, backups, logs, local environments and `.env` files.
- No cloud credentials or connection strings are committed.

These controls reduce accidental exposure. They are not a replacement for Microsoft Entra ID, application roles, formal approval or production security controls.

## Railway staging variables

Do not configure these until a safe database target is available:

```text
PD_MANAGEMENT_ENVIRONMENT=staging
PD_MANAGEMENT_DEPLOYMENT_PROFILE=admin-poc-readonly
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

The joined PostgreSQL path is available in the `admin-poc-readonly` profile. Validation,
mapping and administration data can be viewed there, while their writes, file storage,
audit and role-based authorisation remain deliberately disabled.

### Controlled migration commands

Never put the database password in a command, source file or chat message. The
following form asks for it at a hidden prompt and keeps it out of shell history:

```powershell
python scripts/apply_postgres_migrations.py --host <pooler-host> --user <pooler-user> --prompt-password
python scripts/copy_explorer_to_postgres.py --source data/generated/pd_management_unified.sqlite3
python scripts/copy_explorer_to_postgres.py --source data/generated/pd_management_unified.sqlite3 --apply --host <pooler-host> --user <pooler-user> --prompt-password
```

The middle command is local inspection-only and needs no credentials. The apply command refuses to overwrite
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
- Keep the joined read-only profile enabled.
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

1. Write workflows still require their PostgreSQL persistence, audit and conflict-handling paths to be designed and tested.
2. Source documents, workbook imports and classification backups are written to local paths.
3. Enterprise identity and role-based authorisation are not implemented; the hosted PoC currently uses one shared Basic credential.
4. Supabase backup/recovery remains limited by the selected plan and has not been restore-tested.
5. The joined administration workspace is read-only in Railway by design.
6. Railway's current Asia-Pacific application region is outside Australia, so its acceptability for any TAFE production workload must not be assumed.

## Cutover rule

Do not delete, replace or overwrite the local unified database during these stages. Cloud data begins as a copy and becomes authoritative only after explicit reconciliation, recovery testing and organisational approval.
