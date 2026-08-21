import json
from pathlib import Path

import pytest

from pd_extractor import extract_document
from pd_extractor.extractor import _extract_relationships, _recombine_wrapped_items
from pd_extractor.report import generate_validation_report


SAMPLES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("filename", [
    "10021-01 Facilities Officer - TW4.docx",
    "10218-01 Product Specialist - SEO.docx",
])
def test_sample_produces_contract(filename):
    result = extract_document(SAMPLES / filename)
    assert result["pd_record"]["source_filename"] == filename
    assert isinstance(result["role_description_fields"]["raw_fields"], list)
    assert isinstance(result["extraction_issues"], list)


def test_facilities_relationship_groups_and_capabilities():
    result = extract_document(SAMPLES / "10021-01 Facilities Officer - TW4.docx")
    assert [item["relationship_group"] for item in result["key_relationships"]] == [
        "Internal", "Internal", "Internal", "Internal", "External"
    ]
    focus = [item for item in result["capabilities"] if item["capability_type"] == "Focus"]
    complementary = [item for item in result["capabilities"] if item["capability_type"] == "Complementary"]
    assert len(focus) == 6
    assert len(complementary) == 10
    assert result["capability_field_values"]["Display Resilience and Courage - Type"] == "Focus"
    assert result["capability_field_values"]["Act with Integrity - Type"] == "Complementary"


def test_excluded_metadata_fields_are_omitted():
    result = extract_document(SAMPLES / "10021-01 Facilities Officer - TW4.docx")
    field_names = {item["field_name"] for item in result["role_description_fields"]["raw_fields"]}
    assert "Cluster" not in field_names
    assert "Agency Website" not in field_names
    assert "cluster" not in result["role_description_fields"]
    assert "agency_website" not in result["role_description_fields"]


def test_product_specialist_wrapped_challenges_are_recombined():
    result = extract_document(SAMPLES / "10218-01 Product Specialist - SEO.docx")
    challenges = result["key_challenges"]
    assert len(challenges) == 3
    assert challenges[0]["text"].endswith("dynamic environment.")
    assert challenges[2]["text"].endswith("competing priorities.")


def test_legacy_ministers_office_heading_maps_to_ministerial():
    result = {"key_relationships": []}
    _extract_relationships(
        [["Minister's Office"], ["Who", "Why"], ["Ministerial liaison", "Provide advice"]],
        result,
        "Other / Unclassified",
    )
    assert result["key_relationships"][0]["relationship_group"] == "Ministerial"


@pytest.mark.parametrize(("filename", "expected_title"), [
    ("11317-01 Lead Quality and Self-Assurance Specialist - CEO.docx", "Lead Quality and Self-Assurance Specialist"),
    ("11327-01 Multimedia Officer (Aboriginal Identified) - TWL5.docx", "Multimedia Officer (Aboriginal Identified)"),
    ("11331-01 Quality and Self-Assurance Specialist (Aboriginal Identified) - SEO.docx", "Quality and Self-Assurance Specialist (Aboriginal Identified)"),
    ("11375-01 Director Strategic Policy, Executive and Ministerial Liaison - PSSE Band 1.docx", "Director Strategic Policy, Executive and Ministerial Liaison"),
])
def test_title_variants(filename, expected_title):
    result = extract_document(SAMPLES / filename)
    assert result["pd_record"]["role_title"] == expected_title


def test_inline_key_relationships_heading_is_recovered():
    result = extract_document(SAMPLES / "11327-01 Multimedia Officer (Aboriginal Identified) - TWL5.docx")
    assert len(result["key_relationships"]) == 2
    assert all(item["relationship_group"] == "Internal" for item in result["key_relationships"])
    assert result["key_relationships"][1]["who"] == "Work teams across the business unit"
    assert not result["key_accountabilities"][-1]["text"].endswith("Key relationships")


def test_nested_relationship_cell_text_is_extracted():
    result = extract_document(SAMPLES / "11317-01 Lead Quality and Self-Assurance Specialist - CEO.docx")
    assert result["key_relationships"][1]["who"] == "Faculty and course development teams"


def test_validation_report_contains_document_content(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    result = extract_document(SAMPLES / "10021-01 Facilities Officer - TW4.docx")
    (json_dir / "facilities.json").write_text(json.dumps(result), encoding="utf-8")
    report = generate_validation_report(json_dir, SAMPLES, tmp_path / "report.html")
    content = report.read_text(encoding="utf-8")
    assert "Facilities Officer" in content
    assert "Key relationships" in content
    assert "Display Resilience and Courage" in content


@pytest.mark.parametrize(("filename", "framework", "capability_type", "expected_names"), [
    (
        "10108-01 Alternate Dispute Resolution Specialist - TW9.docx",
        "Human resources",
        "Focus",
        ["Organisational culture", "Workforce Relations"],
    ),
    (
        "10773-02 Chief Financial Officer - PSSE Band 2.docx",
        "Finance",
        "Complementary",
        [
            "Financial Strategy, Governance and Risk Management",
            "Financial Accounting and Statutory Reporting",
            "Management Accounting",
            "Audit and Assurance",
            "Finance Operations and Systems",
            "Finance Business Partnering",
        ],
    ),
])
def test_occupation_specific_capabilities_are_mapped(
    filename, framework, capability_type, expected_names
):
    result = extract_document(SAMPLES / filename)
    occupation = [
        item for item in result["capabilities"]
        if item.get("framework") == framework
    ]
    assert result["pd_record"]["extraction_status"] == "Extraction complete"
    assert [item["capability_name"] for item in occupation] == expected_names
    assert {item["framework"] for item in occupation} == {framework}
    assert {item["capability_type"] for item in occupation} == {capability_type}
    assert all(item["description"] for item in occupation)
    assert all(item["source_text"] for item in occupation)
    assert not result["extraction_issues"]


def test_human_resources_behavioural_indicators_are_preserved():
    result = extract_document(SAMPLES / "10108-01 Alternate Dispute Resolution Specialist - TW9.docx")
    occupation = [item for item in result["capabilities"] if item.get("framework") == "Human resources"]
    assert len(occupation[0]["behavioural_indicators"]) == 8
    assert occupation[0]["level"] == "Level 2"


@pytest.mark.parametrize(("filename", "framework", "capability_type", "names"), [
    (
        "10956-01 Senior Client Systems Engineer - TWL9.docx",
        "Information and Communication Technology (ICT)",
        "Complementary",
        ["Systems Installation / Decommissioning", "Configuration Management"],
    ),
    (
        "11283-01 Director Procurement Strategy and Governance - PSSE Band 1.docx",
        "Procurement",
        "Complementary",
        [
            "Strategic Procurement Leadership", "Procurement Analysis",
            "Procurement Risk Management", "Supplier Relationship Management",
        ],
    ),
])
def test_additional_occupation_frameworks_are_recognised(
    filename, framework, capability_type, names
):
    result = extract_document(SAMPLES / filename)
    occupation = [item for item in result["capabilities"] if item.get("framework") == framework]
    assert [item["capability_name"] for item in occupation] == names
    assert {item["capability_type"] for item in occupation} == {capability_type}
    assert result["pd_record"]["extraction_status"] == "Extraction complete"


def test_sfia_variant_preserves_codes_and_flags_unclassified_type():
    result = extract_document(SAMPLES / "90001-01 Lead UX Researcher - TM1.docx")
    occupation = [
        item for item in result["capabilities"]
        if item.get("framework") == "Information and Communication Technology (ICT)"
    ]
    assert [item["capability_name"] for item in occupation] == [
        "Testing", "User Research", "User Experience Analysis", "User Experience Evaluation",
    ]
    assert [item["capability_code"] for item in occupation] == ["TEST", "URCH", "UNAN", "USEV"]
    assert {item["capability_type"] for item in occupation} == {"Unclassified"}
    assert sum(bool(item["description"]) for item in occupation) == 3
    assert result["pd_record"]["extraction_status"] == "Extraction requires review"
    assert any(
        issue["issue_type"] == "Occupation-specific capability type not identified"
        for issue in result["extraction_issues"]
    )
    assert any(
        issue["description"] == "Key challenges was not extracted"
        for issue in result["extraction_issues"]
    )


def test_director_international_wrapped_list_items_are_recombined():
    result = extract_document(SAMPLES / "10302-01 Director International - TM6.docx")
    assert len(result["key_accountabilities"]) == 12
    assert result["key_accountabilities"][8]["text"].endswith("appropriate strategies and measures.")
    assert result["key_accountabilities"][11]["text"].startswith("Collaborate with staff")
    assert result["key_accountabilities"][11]["text"].endswith("develop the individual.")
    assert len(result["key_challenges"]) == 4
    assert result["key_challenges"][1]["text"].endswith("strategy and model.")
    assert len(result["essential_requirements"]) == 4
    assert result["essential_requirements"][2]["text"].endswith("legislative and regulatory requirements.")


def test_embedded_key_accountabilities_heading_is_split_from_primary_purpose():
    result = extract_document(SAMPLES / "11358-01 Director Agency Alignment and Integration - PSSE Band 1.docx")
    assert result["pd_record"]["role_title"] == "Director Agency Alignment and Integration"
    assert len(result["key_accountabilities"]) == 13
    assert result["sections"]["primary_purpose"].endswith("risks are managed.")
    assert result["key_accountabilities"][0]["text"].startswith("Monitor delivery of key strategic initiatives")
    assert not any(
        issue["description"] == "Key accountabilities was not extracted"
        for issue in result["extraction_issues"]
    )


def test_unpunctuated_but_capitalised_list_item_stays_separate():
    items = _recombine_wrapped_items([
        "A complete bullet without final punctuation",
        "Provide a separate capitalised bullet.",
        "A wrapped sentence ending with",
        "lowercase continuation text.",
    ])
    assert items == [
        "A complete bullet without final punctuation",
        "Provide a separate capitalised bullet.",
        "A wrapped sentence ending with lowercase continuation text.",
    ]
