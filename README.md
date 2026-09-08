# Position Description Extractor

Local prototype for extracting structured data from TAFE NSW Word position descriptions.

## Product map

See [the current-state product map](docs/product-map-current-state.md) for the
screens, audiences, user journeys, product boundaries and known gaps across PD
administration, workforce intelligence and the Career Pathways Explorer.

See [the cloud migration plan](docs/cloud-migration-plan.md) for the staged
GitHub, Railway and Supabase transition and its deployment safeguards.

## Run

```powershell
.\.venv\Scripts\python.exe -m pd_extractor "samples\10021-01 Facilities Officer - TW4.docx" --pretty
```

The JSON is written to standard output. Diagnostics go to standard error.

## Validation report

```powershell
.\.venv\Scripts\python.exe -m pd_extractor.report output\batch
```
# Position Description extractor

Extract Word position descriptions to structured JSON, validate the extraction in HTML,
and import the approved output into a normalized SQLite database.

## Build the prototype database

```powershell
python -m pd_extractor.database .\output\batch `
  --report .\output\database-summary.html
```

The import is idempotent by source filename. Re-importing a position description replaces
its existing database record and related rows rather than creating duplicates.

For human-readable capability browsing, open the `pd_capabilities_readable` database view.
It joins each assignment to its role title, framework and capability name while keeping the
underlying tables normalized.

## Run the validation application

The complete validation editor is integrated into the joined application at
`http://127.0.0.1:8766/validation`. The standalone command below is retained as a
local compatibility entry point:

```powershell
python -m pd_extractor.validation_app
```

Then open `http://127.0.0.1:8765`. Machine-extracted JSON is retained separately from the
editable validation draft. Missing sections remain visible as extraction issues, but a human
validator can confirm legitimate source-document exceptions.

## Career Pathways data build

Import the current role catalogue and activity workbook, validate the canonical source tables,
and rebuild every explorer artifact with one command:

```powershell
python scripts/build_career_pathways.py all
```

For ordinary maintenance after editing `data/source/canonical/`, run the faster build-only form:

```powershell
python scripts/build_career_pathways.py build
```

See `docs/career-pathways-maintenance.md` for the controlled update and release process.
The generated `data/generated/career_pathways.sqlite3` is the complete, versioned audit
snapshot; CSV and JSON files are compatibility exports. To verify snapshot completeness:

```powershell
python scripts/verify_career_pathways_snapshot.py
```

To build the controlled single-database integration candidate for PD Management and the
Career Pathways Explorer:

```powershell
python scripts/build_unified_database.py
```

See `docs/unified-database-integration.md` for data authority, verification and cutover stages.

The PD Management and validation applications now default to the unified database at
`data/generated/pd_management_unified.sqlite3`. Set `PD_MANAGEMENT_DATABASE` or pass
`--database` only when deliberately testing another file.

Refresh the Career Pathways calculations from the maintained data in that same database
and atomically publish them back into it with:

```powershell
python scripts/rebuild_unified_system.py
```

The replacement Constellation nearest-neighbour engine is installed as the
versioned provisional algorithm `constellation-provisional-0.1.0`. Check whether
its maintained inputs are complete with:

```powershell
python -m pd_extractor.pathways.constellation validate
```

See `docs/constellation-algorithm-implementation.md`. The command refuses to
publish incomplete results and leaves the prior neighbour graph untouched.
