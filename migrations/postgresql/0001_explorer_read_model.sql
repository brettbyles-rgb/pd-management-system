-- Read-only PostgreSQL contract for the Career Pathways Explorer.
-- Applied explicitly by scripts/apply_postgres_migrations.py; never at web startup.

CREATE TABLE position_descriptions (
    id BIGINT PRIMARY KEY,
    source_filename TEXT NOT NULL UNIQUE,
    role_title TEXT NOT NULL,
    position_description_no TEXT,
    extraction_status TEXT NOT NULL,
    department_agency TEXT,
    division_branch_unit TEXT,
    classification_grade_band TEXT,
    anzsco_code TEXT,
    osca_code TEXT,
    pcat_code TEXT,
    date_of_approval TEXT,
    senior_executive_work_level_standards TEXT,
    imported_at TEXT NOT NULL,
    role_id TEXT,
    record_status TEXT NOT NULL DEFAULT 'active'
);

CREATE UNIQUE INDEX position_descriptions_role_id_uq
    ON position_descriptions(role_id) WHERE role_id IS NOT NULL;

CREATE TABLE classification_references (
    id BIGINT PRIMARY KEY,
    raw_label TEXT NOT NULL UNIQUE,
    display_label TEXT NOT NULL,
    abbreviation TEXT,
    cohort TEXT,
    seniority_order DOUBLE PRECISION,
    enterprise_agreement TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE job_family_import_batches (
    id BIGINT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_path TEXT,
    framework_sheet TEXT NOT NULL,
    mapping_sheet TEXT NOT NULL,
    framework_rows INTEGER NOT NULL DEFAULT 0,
    mapping_rows INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    imported_at TEXT NOT NULL
);

CREATE TABLE job_family_entries (
    id BIGINT PRIMARY KEY,
    import_batch_id BIGINT NOT NULL REFERENCES job_family_import_batches(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    parent_code TEXT,
    main_definition TEXT,
    supp_definition_1 TEXT,
    supp_definition_2 TEXT,
    exclusions TEXT,
    sequence INTEGER NOT NULL,
    UNIQUE(import_batch_id, code)
);

CREATE TABLE pd_job_family_mappings (
    id BIGINT PRIMARY KEY,
    import_batch_id BIGINT NOT NULL REFERENCES job_family_import_batches(id) ON DELETE CASCADE,
    position_description_id BIGINT REFERENCES position_descriptions(id) ON DELETE SET NULL,
    pd_id TEXT NOT NULL,
    position_title TEXT,
    position_grade TEXT,
    mapping_rank INTEGER NOT NULL,
    mapping_code TEXT,
    mapping_name TEXT,
    mapping_level TEXT,
    mapping_validated TEXT,
    validation_notes TEXT,
    framework_code_valid INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE activity_definitions (
    id TEXT PRIMARY KEY,
    match_label TEXT NOT NULL UNIQUE,
    plain_label TEXT NOT NULL,
    discriminating INTEGER NOT NULL,
    cluster_id INTEGER,
    raw_count INTEGER NOT NULL DEFAULT 0,
    role_count INTEGER NOT NULL DEFAULT 0,
    role_share DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    cluster_member_phrases TEXT
);

CREATE TABLE activity_statistics (
    activity_id TEXT,
    activity_label TEXT,
    roles_with_activity TEXT,
    total_active_roles TEXT,
    share TEXT,
    rarity_weight TEXT,
    source_release TEXT,
    build_version TEXT,
    algorithm_version TEXT
);

CREATE TABLE position_description_activities (
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    activity_id TEXT NOT NULL REFERENCES activity_definitions(id) ON DELETE CASCADE,
    activity_rank INTEGER NOT NULL CHECK(activity_rank BETWEEN 1 AND 14),
    source TEXT NOT NULL DEFAULT 'activity_pipeline',
    created_at TEXT NOT NULL,
    PRIMARY KEY(position_description_id, activity_id)
);

CREATE TABLE activity_assignment_gaps (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    gap_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE capability_frameworks (
    id BIGINT PRIMARY KEY,
    framework_name TEXT NOT NULL UNIQUE
);

CREATE TABLE capability_definitions (
    id BIGINT PRIMARY KEY,
    framework_id BIGINT NOT NULL REFERENCES capability_frameworks(id),
    capability_name TEXT NOT NULL,
    capability_code TEXT,
    UNIQUE(framework_id, capability_name)
);

CREATE TABLE pd_capabilities (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    capability_definition_id BIGINT NOT NULL REFERENCES capability_definitions(id),
    sequence INTEGER NOT NULL,
    capability_type TEXT NOT NULL,
    required_level TEXT NOT NULL,
    capability_group TEXT,
    description TEXT,
    source_text TEXT
);

CREATE TABLE pathway_capability_identities (
    capability_id TEXT,
    framework_id TEXT,
    source_capability_id TEXT,
    source_framework_id TEXT,
    framework_name TEXT,
    capability_code TEXT,
    capability_name TEXT
);

CREATE TABLE capability_level_rules (
    framework_name TEXT,
    raw_level TEXT,
    normalized_level TEXT,
    assignment_count TEXT,
    interpretation_status TEXT
);

CREATE TABLE role_neighbours (
    role_id TEXT,
    pd_id TEXT,
    pd_title TEXT,
    neighbour_role_id TEXT,
    neighbour_pd_id TEXT,
    neighbour_title TEXT,
    neighbour_rank TEXT,
    grade_step_dg TEXT,
    readiness_rdy TEXT,
    work_similarity_cr TEXT,
    same_subfamily_ssub TEXT,
    grade_proximity_gp TEXT,
    readiness_contribution TEXT,
    activity_contribution TEXT,
    subfamily_contribution TEXT,
    classification_contribution TEXT,
    score TEXT,
    source_release TEXT,
    build_version TEXT,
    algorithm_version TEXT
);

CREATE TABLE constellation_algorithm_versions (
    algorithm_version TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('configured','ready','published','superseded')),
    created_at_utc TEXT NOT NULL,
    specification_name TEXT NOT NULL,
    configuration_name TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE constellation_candidate_scores (
    algorithm_version TEXT NOT NULL REFERENCES constellation_algorithm_versions(algorithm_version),
    source_release TEXT NOT NULL,
    source_role_id TEXT NOT NULL,
    candidate_role_id TEXT NOT NULL,
    shared_activity_count INTEGER NOT NULL,
    activity_union_count INTEGER NOT NULL,
    act_plain DOUBLE PRECISION NOT NULL,
    act_rare DOUBLE PRECISION NOT NULL,
    occupational_proximity DOUBLE PRECISION NOT NULL,
    adjacency_tier INTEGER,
    family_adjacency DOUBLE PRECISION NOT NULL,
    grade_delta INTEGER,
    grade_proximity DOUBLE PRECISION NOT NULL,
    act_plain_contribution DOUBLE PRECISION NOT NULL,
    act_rare_contribution DOUBLE PRECISION NOT NULL,
    occupational_contribution DOUBLE PRECISION NOT NULL,
    adjacency_contribution DOUBLE PRECISION NOT NULL,
    grade_contribution DOUBLE PRECISION NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    above_floor INTEGER NOT NULL CHECK(above_floor IN (0,1)),
    eligible_default INTEGER NOT NULL CHECK(eligible_default IN (0,1)),
    eligible_allow_down INTEGER NOT NULL CHECK(eligible_allow_down IN (0,1)),
    exclusion_reason_default TEXT,
    exclusion_reason_allow_down TEXT,
    rank_default INTEGER,
    rank_allow_down INTEGER,
    PRIMARY KEY (algorithm_version, source_role_id, candidate_role_id)
);

CREATE INDEX role_neighbours_source_rank_idx
    ON role_neighbours(role_id, neighbour_rank);
CREATE INDEX role_neighbours_target_idx ON role_neighbours(neighbour_role_id);
CREATE INDEX constellation_scores_default_rank
    ON constellation_candidate_scores(algorithm_version, source_role_id, rank_default);

CREATE VIEW job_family_nodes AS
SELECT e.code, e.name, e.level, e.parent_code, e.main_definition,
       e.supp_definition_1, e.supp_definition_2, e.exclusions, e.sequence
FROM job_family_entries e
JOIN job_family_import_batches b ON b.id = e.import_batch_id
WHERE b.is_active = 1;

CREATE VIEW activities AS
SELECT id AS activity_id, match_label AS canonical_match_label,
       plain_label AS canonical_plain_label,
       CASE discriminating WHEN 1 THEN 'Yes' ELSE 'No' END AS discriminating,
       CAST(cluster_id AS TEXT) AS cluster_id,
       CAST(raw_count AS TEXT) AS raw_count,
       cluster_member_phrases
FROM activity_definitions;

CREATE VIEW role_activities AS
SELECT p.role_id, a.position_description_id,
       p.position_description_no AS pd_number, p.role_title AS title,
       a.activity_rank, a.activity_id,
       COALESCE((
           SELECT STRING_AGG(g.gap_text, ' | ' ORDER BY g.id)
           FROM activity_assignment_gaps g
           WHERE g.position_description_id = a.position_description_id
       ), '') AS assignment_gaps,
       '0' AS retry_count, 'No' AS fallback_used
FROM position_description_activities a
JOIN position_descriptions p ON p.id = a.position_description_id;

CREATE VIEW capabilities AS SELECT * FROM pathway_capability_identities;

CREATE VIEW role_capabilities AS
SELECT p.role_id, i.capability_id, CAST(pc.id AS TEXT) AS source_assignment_id,
       pc.position_description_id, pc.sequence, pc.capability_type,
       f.framework_name, d.capability_code, d.capability_name,
       pc.required_level, r.normalized_level, pc.capability_group,
       pc.description, pc.source_text
FROM pd_capabilities pc
JOIN position_descriptions p ON p.id = pc.position_description_id
JOIN capability_definitions d ON d.id = pc.capability_definition_id
JOIN capability_frameworks f ON f.id = d.framework_id
JOIN pathway_capability_identities i
  ON CAST(i.source_capability_id AS BIGINT) = d.id
LEFT JOIN capability_level_rules r
  ON r.framework_name = f.framework_name AND r.raw_level = pc.required_level;

CREATE VIEW role_job_family_mappings AS
SELECT p.role_id, m.position_description_id,
       m.pd_id AS legacy_mapping_pd_id, m.mapping_rank, m.mapping_code,
       m.mapping_name, m.mapping_level, m.mapping_validated,
       m.validation_notes, m.framework_code_valid
FROM pd_job_family_mappings m
JOIN job_family_import_batches b
  ON b.id = m.import_batch_id AND b.is_active = 1
LEFT JOIN position_descriptions p ON p.id = m.position_description_id;
