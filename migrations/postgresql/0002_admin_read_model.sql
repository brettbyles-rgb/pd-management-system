-- Additional read model required by the PD administration and mapping screens.
-- Routes remain disabled in the public explorer-demo deployment profile.

CREATE TABLE role_description_fields (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    field_value TEXT NOT NULL
);

CREATE TABLE pd_sections (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    section_text TEXT NOT NULL,
    UNIQUE(position_description_id, section_name)
);

CREATE TABLE pd_list_items (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    item_text TEXT NOT NULL
);

CREATE TABLE key_relationships (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    relationship_group TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    who TEXT NOT NULL,
    why TEXT NOT NULL
);

CREATE TABLE capability_indicators (
    id BIGINT PRIMARY KEY,
    pd_capability_id BIGINT NOT NULL REFERENCES pd_capabilities(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    indicator_text TEXT NOT NULL
);

CREATE TABLE extraction_issues (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    issue_type TEXT NOT NULL,
    field_or_section TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL
);

CREATE TABLE validation_records (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL UNIQUE REFERENCES position_descriptions(id) ON DELETE CASCADE,
    extracted_json TEXT NOT NULL,
    draft_json TEXT NOT NULL,
    section_statuses_json TEXT NOT NULL DEFAULT '{}',
    edited_paths_json TEXT NOT NULL DEFAULT '[]',
    validation_status TEXT NOT NULL DEFAULT 'Not validated',
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    validated_at TEXT
);

CREATE TABLE validation_events (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_details TEXT,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT)
);

CREATE TABLE pd_assigned_job_family_mappings (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
    mapping_rank INTEGER NOT NULL CHECK(mapping_rank BETWEEN 1 AND 3),
    mapping_code TEXT NOT NULL,
    mapping_name TEXT NOT NULL,
    mapping_level TEXT NOT NULL,
    mapping_validated TEXT NOT NULL DEFAULT 'Yes',
    validation_notes TEXT,
    assigned_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    UNIQUE(position_description_id, mapping_rank),
    UNIQUE(position_description_id, mapping_code)
);

CREATE TABLE pd_mapping_texts (
    id BIGINT PRIMARY KEY,
    position_description_id BIGINT NOT NULL UNIQUE REFERENCES position_descriptions(id) ON DELETE CASCADE,
    generator_version TEXT NOT NULL,
    title_text TEXT NOT NULL,
    purpose_text TEXT NOT NULL,
    accountabilities_text TEXT NOT NULL,
    knowledge_text TEXT NOT NULL,
    requirements_text TEXT NOT NULL,
    full_text TEXT NOT NULL,
    excluded_items_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT)
);

CREATE TABLE embeddings (
    id BIGINT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    source_text_hash TEXT NOT NULL,
    source_text TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::TEXT),
    UNIQUE(source_type, source_id, model_name)
);

CREATE INDEX pd_list_items_position_idx ON pd_list_items(position_description_id, section_name);
CREATE INDEX key_relationships_position_idx ON key_relationships(position_description_id);
CREATE INDEX assigned_mappings_position_idx ON pd_assigned_job_family_mappings(position_description_id);
CREATE INDEX mapping_texts_position_idx ON pd_mapping_texts(position_description_id);
CREATE INDEX embeddings_source_idx ON embeddings(source_type, source_id, model_name);
CREATE INDEX embeddings_model_idx ON embeddings(model_name);

CREATE VIEW pd_capabilities_readable AS
SELECT pc.id AS pd_capability_id, pd.id AS position_description_id,
       pd.role_title, pd.position_description_no, pc.sequence,
       pc.capability_type, cf.framework_name AS framework,
       cd.capability_name, cd.capability_code, pc.required_level,
       pc.capability_group, pc.description, pc.source_text
FROM pd_capabilities pc
JOIN position_descriptions pd ON pd.id = pc.position_description_id
JOIN capability_definitions cd ON cd.id = pc.capability_definition_id
JOIN capability_frameworks cf ON cf.id = cd.framework_id;

CREATE VIEW active_job_family_entries AS
SELECT entry.*
FROM job_family_entries entry
JOIN job_family_import_batches batch ON batch.id = entry.import_batch_id
WHERE batch.is_active = 1;

CREATE VIEW active_pd_job_family_mappings AS
SELECT mapping.id, mapping.import_batch_id, mapping.position_description_id,
       mapping.pd_id, mapping.position_title, mapping.position_grade,
       mapping.mapping_rank, mapping.mapping_code, mapping.mapping_name,
       mapping.mapping_level, mapping.mapping_validated,
       mapping.validation_notes, mapping.framework_code_valid
FROM pd_job_family_mappings mapping
JOIN job_family_import_batches batch ON batch.id = mapping.import_batch_id
WHERE batch.is_active = 1
  AND NOT EXISTS (
      SELECT 1 FROM pd_assigned_job_family_mappings assigned
      WHERE assigned.position_description_id = mapping.position_description_id
  )
UNION ALL
SELECT -assigned.id AS id, NULL::BIGINT AS import_batch_id,
       assigned.position_description_id,
       SUBSTR(pd.position_description_no, 1, 5) AS pd_id,
       pd.role_title AS position_title,
       pd.classification_grade_band AS position_grade,
       assigned.mapping_rank, assigned.mapping_code, assigned.mapping_name,
       assigned.mapping_level, assigned.mapping_validated,
       assigned.validation_notes, 1 AS framework_code_valid
FROM pd_assigned_job_family_mappings assigned
JOIN position_descriptions pd ON pd.id = assigned.position_description_id;

-- Supabase API roles receive no access without explicit policies. The backend's
-- direct PostgreSQL owner connection continues to work during this staging phase.
ALTER TABLE position_descriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE classification_references ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_family_import_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_family_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE pd_job_family_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_statistics ENABLE ROW LEVEL SECURITY;
ALTER TABLE position_description_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_assignment_gaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_frameworks ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pd_capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE pathway_capability_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_level_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_neighbours ENABLE ROW LEVEL SECURITY;
ALTER TABLE constellation_algorithm_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE constellation_candidate_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_description_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE pd_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE pd_list_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE key_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE capability_indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_issues ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pd_assigned_job_family_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE pd_mapping_texts ENABLE ROW LEVEL SECURITY;
ALTER TABLE embeddings ENABLE ROW LEVEL SECURITY;
