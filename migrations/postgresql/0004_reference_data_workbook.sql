BEGIN;

CREATE TABLE job_family_adjacency_entries (
    import_batch_id BIGINT NOT NULL REFERENCES job_family_import_batches(id) ON DELETE CASCADE,
    source_family_code TEXT NOT NULL,
    target_family_code TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK(tier IN (0, 1, 2)),
    rationale TEXT,
    PRIMARY KEY (import_batch_id, source_family_code, target_family_code),
    FOREIGN KEY (import_batch_id, source_family_code)
        REFERENCES job_family_entries(import_batch_id, code),
    FOREIGN KEY (import_batch_id, target_family_code)
        REFERENCES job_family_entries(import_batch_id, code)
);

CREATE VIEW active_job_family_adjacency
WITH (security_invoker = true) AS
SELECT adjacency.source_family_code, adjacency.target_family_code,
       adjacency.tier, adjacency.rationale
FROM job_family_adjacency_entries adjacency
JOIN job_family_import_batches batch ON batch.id = adjacency.import_batch_id
WHERE batch.is_active = 1;

ALTER TABLE job_family_adjacency_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY pd_management_reader_select
    ON job_family_adjacency_entries FOR SELECT TO pd_management_reader USING (true);

GRANT SELECT ON job_family_adjacency_entries, active_job_family_adjacency
    TO pd_management_reader;

COMMIT;
