# Career Pathways canonical data model

The logical model is relational. Maintained role facts and relationships live in `data/source/canonical/`; taxonomies and interpretation rules live in `data/reference/`; all algorithm and application artifacts live in `data/generated/`.

`roles(role_id)` is the parent of role capabilities, activities, requirements, applicability, family mappings and generated graph edges. `role_id` is a stored UUID. The initial UUID is deterministically bootstrapped from the catalogue database primary key, then persisted in `roles.csv`; later imports reuse the persisted mapping.

Core entities:

- `roles`: stable identity, PD business number, title, classification alias and provenance.
- `classification_aliases`: raw-to-display classification mapping, cohort and seniority order.
- `job_family_nodes`: hierarchy nodes with parent codes; `role_job_family_mappings` retains ranks and alternatives.
- `capability_frameworks`, `capabilities`, `role_capabilities`: original framework, code, name and raw level. `normalized_level` is a separate calculated interpretation.
- `capability_level_rules`: observed raw formats, numeric interpretations and review status.
- `capability_applicability`: explicit `applicable`, `not_applicable` or `review_required`; absence is never silently treated as not applicable.
- `activities`, `role_activities`: vocabulary and role assignments.
- `essential_requirements`: mandatory/essential items extracted from supplied PDs.
- `adjacency_rules`: reserved maintained family/occupation rules; currently empty rather than guessed.
- `source_release.json`, `build_config.json`: input hashes, counts, build version and calculation configuration.
- `activity_rarity`: stored corpus share and rarity weight for every role/activity assignment.
- `role_capability_profiles`: the exact normalized capability features consumed by scoring.
- `role_neighbours`: ranked recommendations with every raw component, weighted contribution and final score.
- `algorithm_parameters`, `build_metadata`, `release_files`: the exact rules, versions and input hashes needed to reproduce a release.
- `role_application_payloads`, `role_purposes`, `key_accountabilities`: the complete structured application data included in the published snapshot.

The SQLite file is the complete release snapshot. Generated CSV and JSON files are compatibility and interchange exports, not the sole location of any algorithm input or result. Audit-friendly views (`role_activity_audit`, `role_capability_audit`, and `role_neighbour_audit`) expose readable role-level records without requiring joins.

Generated graph scoring is transparent and provisional. It exists to make all outputs reproducible from one release; final pathway-selection tuning is deliberately deferred.
