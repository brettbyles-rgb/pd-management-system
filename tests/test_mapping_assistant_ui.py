from __future__ import annotations

from pd_extractor.database import connect_database, initialise_database
from pd_extractor.mapping_assistant_ui import (
    build_mapping_assistant_payload,
    render_mapping_assistant,
)


def test_mapping_assistant_payload_uses_live_framework_hierarchy_and_roster(tmp_path):
    connection = connect_database(tmp_path / "mapping-ui.sqlite3")
    initialise_database(connection)
    try:
        connection.execute(
            """INSERT INTO position_descriptions(
                   id, source_filename, role_title, position_description_no,
                   extraction_status, classification_grade_band
               ) VALUES
               (1, 'target.docx', 'Target role', '10001-01', 'Complete', 'TWL4'),
               (2, 'evidence.docx', 'Evidence role', '10002-01', 'Complete', 'TWL5')"""
        )
        connection.execute(
            """INSERT INTO classification_references(
                   raw_label, display_label, abbreviation, cohort, seniority_order
               ) VALUES
               ('TWL4', 'TAFE Worker Level 4', 'TWL4', 'TWL1-TWL4', 40),
               ('TWL5', 'TAFE Worker Level 5', 'TWL5', 'TWL5-TWL7', 50)"""
        )
        connection.execute(
            """INSERT INTO pd_sections(position_description_id, section_name, section_text)
               VALUES (2, 'primary_purpose', 'Provide evidence for the preview.')"""
        )
        connection.executemany(
            """INSERT INTO pd_list_items(
                   position_description_id, section_name, sequence, item_text
               ) VALUES (2, 'key_accountabilities', ?, ?)""",
            [(1, "First"), (2, "Second"), (3, "Third"), (4, "Fourth")],
        )
        connection.execute(
            """INSERT INTO job_family_import_batches(
                   id, source_filename, framework_sheet, mapping_sheet, is_active
               ) VALUES (1, 'test.xlsx', 'job_family_power_query', 'job_mapping_input', 1)"""
        )
        connection.executemany(
            """INSERT INTO job_family_entries(
                   import_batch_id, code, name, level, parent_code,
                   main_definition, sequence
               ) VALUES (1, ?, ?, ?, ?, ?, ?)""",
            [
                ("1000000000", "FAMILY", "Job Family", "", "Family definition", 1),
                ("1000001000", "SUB", "Sub-family", "1000000000", "Sub definition", 2),
                # The adapter repairs a malformed family-level parent for a specialisation.
                ("1000001001", "SPEC", "Specialisation", "1000000000", "Spec definition", 3),
            ],
        )
        connection.execute(
            """INSERT INTO pd_job_family_mappings(
                   import_batch_id, position_description_id, pd_id, mapping_rank,
                   mapping_code, mapping_name, mapping_level, mapping_validated,
                   framework_code_valid
               ) VALUES (1, 2, '10002', 1, '1000001001', 'SPEC',
                         'Specialisation', 'Yes', 1)"""
        )
        detail = {
            "id": 1,
            "position_description_no": "10001-01",
            "role_title": "Target role",
            "classification_abbreviation": "TWL4",
            "classification_cohort": "TWL1-TWL4",
        }
        similar = [{
            "position_description_id": 2,
            "position_description_no": "10002-01",
            "role_title": "Evidence role",
            "similarity": 0.9,
            "mapping_validated": "Yes",
            "mapping_hierarchy": [
                {"code": "1000000000", "name": "FAMILY", "level": "Job Family"},
                {"code": "1000001000", "name": "SUB", "level": "Sub-family"},
                {"code": "1000001001", "name": "SPEC", "level": "Specialisation"},
            ],
        }]
        framework_scores = {
            "1000000000": {
                "code": "1000000000", "name": "FAMILY", "level": "Job Family",
                "parent_code": "", "main_definition": "Family definition",
                "framework_similarity": 0.7,
            },
            "1000001000": {
                "code": "1000001000", "name": "SUB", "level": "Sub-family",
                "parent_code": "1000000000", "main_definition": "Sub definition",
                "framework_similarity": 0.7,
            },
            "1000001001": {
                "code": "1000001001", "name": "SPEC", "level": "Specialisation",
                "parent_code": "1000000000", "main_definition": "Spec definition",
                "framework_similarity": 0.7,
            },
        }

        payload = build_mapping_assistant_payload(
            connection, detail, [], similar, framework_scores
        )

        assert payload["PD"]["databaseId"] == 1
        assert payload["FAMILIES"][0]["name"] == "FAMILY"
        assert payload["FAMILIES"][0]["subs"][0]["name"] == "SUB"
        assert payload["FAMILIES"][0]["subs"][0]["specs"][0]["name"] == "SPEC"
        assert payload["ROSTER"]["1000001001"]["roles"][0]["pd"] == "10002-01"
        assert payload["PDDETAIL"]["10002-01"]["acc"] == ["First", "Second", "Third"]
        assert payload["PDDETAIL"]["10002-01"]["accTotal"] == 4
    finally:
        connection.close()


def test_mapping_assistant_template_preserves_reference_and_wires_live_assignment():
    html = render_mapping_assistant({
        "PD": {"databaseId": 7, "id": "10001-01"},
        "FAMILIES": [],
        "ROSTER": {},
        "PDDETAIL": {},
    })

    assert "window.__MAPPING_DATA__" in html
    assert "Recommended job families" in html
    assert "Review shortlist &amp; assign" in html
    assert "s>=0.85?'Strong':s>=0.75?'Good':s>=0.50?'Possible':'Weak'" in html
    assert "PD.databaseId" in html
    assert "mapping_codes:ordered.map(x=>x.node.id)" in html
    assert 'href="/#upload"' in html
    assert 'href="/#library"' in html
    assert 'href="/mapping-assistant"' in html
    assert 'href="/admin/classifications"' in html
    assert 'href="/#workbook"' in html
