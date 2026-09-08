# Governed reference-data workbook

## Purpose

The reference-data workbook is the controlled round trip for three related datasets:

1. the job-family framework hierarchy;
2. role-to-job-family mappings, including up to three ranked mappings; and
3. the directed job-family adjacency matrix used by the Constellation algorithm.

These datasets are versioned and activated together so the framework, mappings and
matrix cannot silently drift into incompatible releases.

## Workbook sheets

| Sheet | Contents | Key controls |
| --- | --- | --- |
| `job_family_power_query` | Code, name, hierarchy level, parent and definitions | Unique codes, existing parents and no hierarchy cycles |
| `job_mapping_input` | One role row with primary and up to two secondary mappings | Unique PD IDs and mapping codes that exist in the framework; names and levels are regenerated from the framework on apply |
| `job_family_adjacency` | A square Job Family × Job Family matrix | Every cell required; values only `0`, `1` or `2`; diagonal must be `0` |
| `README` | Workbook purpose and editing instructions | Informational; regenerated on download |

Adjacency is directed. A difference between A → B and B → A is allowed but appears
as a validation warning so it must be deliberate.

## Application workflow

1. Open **Reference Data Workbook** from the joined application.
2. Select **Download current workbook**. Always begin from a fresh download.
3. Edit the three governed sheets without renaming sheets or header rows.
4. Select the file and choose **Validate workbook**.
5. Review the current-versus-workbook counts, errors and warnings.
6. In the writable local profile, choose **Apply validated workbook**.

Railway remains deliberately read-only. It permits authenticated download and safe
validation previews, but blocks apply. This prevents a write-capable Supabase credential
from being stored in the public web service.

## Controlled Supabase maintenance

First apply any unapplied schema migrations using the Supabase owner/maintenance
account. Use the visible password option if required:

```powershell
.\.venv\Scripts\python.exe scripts\apply_postgres_migrations.py `
  --host <supabase-pooler-host> `
  --user <supabase-owner-user> `
  --visible-password
```

Preview a workbook without changing data:

```powershell
.\.venv\Scripts\python.exe scripts\apply_reference_workbook.py .\reference-data.xlsx `
  --host <supabase-pooler-host> `
  --user <supabase-owner-user> `
  --visible-password
```

Only after reviewing a successful preview, apply the same workbook:

```powershell
.\.venv\Scripts\python.exe scripts\apply_reference_workbook.py .\reference-data.xlsx `
  --apply `
  --host <supabase-pooler-host> `
  --user <supabase-owner-user> `
  --visible-password
```

The password is used only to establish the TLS database session. It is not placed in
the workbook, source code, command history or application logs.

## Transaction and recovery behaviour

- Validation is read-only and happens before apply.
- Apply takes an exclusive lock over the four reference tables.
- The framework, mappings and adjacency matrix are inserted in one transaction.
- The new batch becomes active only as part of that transaction.
- Any database error rolls back the entire replacement.
- Prior import batches remain stored. A prior exported workbook can be validated and
  reapplied as a new active release if rollback is required.
- Manual Mapping Assistant overrides are folded into the downloaded effective mapping
  list. Applying a workbook clears those overrides because the workbook becomes the
  complete mapping authority for that release.

Refreshing these maintained inputs does not automatically regenerate embeddings or
career-pathway candidate scores. Those derived datasets must be rebuilt and reviewed
as a separate publication step.
