# Maintaining Career Pathways data

## One-command rebuild

After editing the maintained CSV tables, run:

```powershell
python scripts/build_career_pathways.py build
```

To re-import the current catalogue database and activity workbook, preserving existing `role_id` values, then rebuild everything:

```powershell
python scripts/build_career_pathways.py all
```

## Add or change a role

1. Add or update one row in `data/source/canonical/roles.csv`. Assign a new UUID once for a genuinely new role; never reuse or renumber an existing `role_id`.
2. Update its classification, ranked job-family mappings, capability applicability, capabilities, activities and essential requirements in the corresponding canonical tables.
3. Retire a role by setting `record_status=retired`; do not delete or recycle its identity.
4. Run the build command.
5. Review `data/qa/validation_summary.json`, `exceptions.csv`, `business_owner_review.csv`, `reconciliation.json` and `change_report.md`.
6. Publish only when exceptions are accepted/resolved and all generated files share source release `f2fd372bffce0fa9`.

The build performs a complete rebuild. Generated CSV, JSON and SQLite artifacts must never be manually edited.

The SQLite database is a self-contained release snapshot containing canonical inputs, derived algorithm features, configuration, lineage hashes and recommendation outputs. Verify it with:

```powershell
python scripts/verify_career_pathways_snapshot.py
```
