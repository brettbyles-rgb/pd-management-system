from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from docx import Document
from docx.document import Document as DocumentType
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P


SECTION_ALIASES = {
    "agency overview": "agency_overview",
    "primary purpose of the role": "primary_purpose",
    "key accountabilities": "key_accountabilities",
    "key challenges": "key_challenges",
    "key relationships": "key_relationships",
    "role dimensions": "role_dimensions",
    "decision making": "decision_making",
    "reporting line": "reporting_line",
    "direct reports": "direct_reports",
    "budget/expenditure": "budget_expenditure",
    "key knowledge and experience": "key_knowledge_and_experience",
    "essential requirements": "essential_requirements",
    "capabilities for the role": "capabilities_for_the_role",
    "focus capabilities": "focus_capabilities",
    "complementary capabilities": "complementary_capabilities",
}

LEVELS = {"foundational", "intermediate", "adept", "advanced", "highly advanced"}
EXCLUDED_METADATA_FIELDS = {"cluster", "agency website"}
CAPABILITY_NAMES = [
    "Display Resilience and Courage", "Act with Integrity", "Manage Self",
    "Value Diversity and Inclusion", "Communicate Effectively",
    "Commit to Customer Service", "Work Collaboratively", "Influence and Negotiate",
    "Deliver Results", "Plan and Prioritise", "Think and Solve Problems",
    "Demonstrate Accountability", "Finance", "Technology",
    "Procurement and Contract Management", "Project Management",
    "Manage and Develop People", "Inspire Direction and Purpose",
    "Optimise Business Outcomes", "Manage Reform and Change",
]
CAPABILITIES = {name.lower(): name for name in CAPABILITY_NAMES}
PUBLIC_SECTOR_FRAMEWORK = "NSW Public Sector Capability Framework"
OCCUPATION_FRAMEWORK_SIGNATURES = {
    "Finance": {
        "financial strategy governance and risk management",
        "financial accounting and statutory reporting",
        "management accounting",
        "audit and assurance",
        "finance operations and systems",
        "finance business partnering",
    },
    "Human resources": {
        "organisational culture",
        "organizational culture",
        "workforce relations",
    },
    "Procurement": {
        "strategic procurement leadership",
        "procurement analysis",
        "procurement risk management",
        "supplier relationship management",
    },
    "Information and Communication Technology (ICT)": {
        "systems installation decommissioning",
        "configuration management",
        "testing",
        "user research",
        "user experience analysis",
        "user experience evaluation",
    },
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).strip()


def _paragraph_text(paragraph: Paragraph) -> str:
    return _clean("".join(paragraph._p.xpath(".//w:t/text()")))


def _iter_blocks(document: DocumentType) -> Iterator[Paragraph | Table]:
    def walk(parent: Any) -> Iterator[Paragraph | Table]:
        for child in parent.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, document)
            elif isinstance(child, CT_Tbl):
                yield Table(child, document)
            else:
                yield from walk(child)

    yield from walk(document.element.body)


def _table_rows(table: Table) -> list[list[str]]:
    return [
        [_cell_text(cell) for cell in row.cells]
        for row in table.rows
    ]


def _cell_text(cell: Any) -> str:
    paragraphs = []
    for paragraph in cell._tc.xpath(".//w:p"):
        text = _clean("".join(paragraph.xpath(".//w:t/text()")))
        if text:
            paragraphs.append(text)
    return _clean(" ".join(paragraphs))


def _heading(text: str) -> str | None:
    key = _key(text)
    for label, canonical in SECTION_ALIASES.items():
        if key == _key(label):
            return canonical
    return None


def _split_embedded_heading(text: str) -> tuple[str, str, str] | None:
    """Find a section heading embedded after content in the same text block."""
    candidates = [
        label for label, canonical in SECTION_ALIASES.items()
        if canonical in {
            "key_accountabilities", "key_challenges", "key_relationships",
            "role_dimensions", "key_knowledge_and_experience", "essential_requirements",
            "capabilities_for_the_role",
        }
    ]
    pattern = "|".join(re.escape(label) for label in sorted(candidates, key=len, reverse=True))
    match = re.search(rf"(?i)(?<!^)(?P<heading>{pattern})(?=\s|$)", text)
    if not match:
        return None
    before = _clean(text[:match.start()])
    heading = text[match.start():match.end()]
    after = _clean(text[match.end():])
    return before, heading, after


def _append_section_text(
    section_text: dict[str, list[str]], current: str, text: str
) -> str:
    remaining = text
    active = current
    while remaining:
        embedded = _split_embedded_heading(remaining)
        if embedded is None:
            section_text.setdefault(active, []).extend(
                line for line in remaining.splitlines() if _clean(line)
            )
            break
        before, heading, after = embedded
        if before:
            section_text.setdefault(active, []).extend(
                line for line in before.splitlines() if _clean(line)
            )
        active = _heading(heading) or active
        remaining = after
    return active


def _is_occupation_specific_heading(text: str) -> bool:
    key = _key(text)
    words = key.split()
    if len(words) > 9:
        return False
    if "capabilities" not in words and "capability" not in words:
        return False
    if words[:2] not in (["occupation", "specific"], ["occupational", "specific"]):
        if words[:3] != ["occupation", "profession", "specific"]:
            return False
    allowed = {
        "occupation", "occupational", "specific", "capability", "capabilities",
        "profession", "set", "skills", "framework", "information", "age", "sfia",
        "focus", "complementary", "complimentary",
    }
    return all(word in allowed for word in words)


def _occupation_capability_type(text: str) -> str:
    words = set(_key(text).split())
    if "focus" in words:
        return "Focus"
    if "complementary" in words or "complimentary" in words:
        return "Complementary"
    return "Unclassified"


def _empty_result(path: Path) -> dict[str, Any]:
    fields = {}
    for name in CAPABILITY_NAMES:
        fields[f"{name} - Type"] = ""
        fields[f"{name} - Level"] = ""
    return {
        "pd_record": {"role_title": "", "source_filename": path.name,
                      "extraction_status": "Extraction requires review", "extraction_warnings": []},
        "role_description_fields": {"raw_fields": []},
        "sections": {"primary_purpose": "", "decision_making": "", "reporting_line": "",
                     "direct_reports": "", "budget_expenditure": ""},
        "key_accountabilities": [], "key_challenges": [], "key_relationships": [],
        "key_knowledge_and_experience": [], "essential_requirements": [],
        "capabilities": [], "capability_field_values": fields, "extraction_issues": [],
    }


def extract_document(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    doc = Document(path)
    result = _empty_result(path)
    blocks = list(_iter_blocks(doc))

    paragraphs = [_paragraph_text(p) for p in blocks if isinstance(p, Paragraph) and _paragraph_text(p)]
    for index, text in enumerate(paragraphs):
        if _key(text) == "role description" and index + 1 < len(paragraphs):
            candidate = paragraphs[index + 1]
            if not _heading(candidate):
                result["pd_record"]["role_title"] = candidate
                break

    tables = [block for block in blocks if isinstance(block, Table)]
    if tables:
        rows = _table_rows(tables[0])
        sequence = 0
        for row in rows:
            if len(row) < 2 or not row[0] or _key(row[0]) in {"role description fields", "details"}:
                continue
            if _key(row[0]) in EXCLUDED_METADATA_FIELDS:
                continue
            sequence += 1
            result["role_description_fields"]["raw_fields"].append(
                {"sequence": sequence, "field_name": row[0], "field_value": row[1]}
            )
            mapped = re.sub(r"[^a-z0-9]+", "_", row[0].lower()).strip("_")
            result["role_description_fields"][mapped] = row[1]

    current: str | None = None
    relationship_group = "Other / Unclassified"
    section_text: dict[str, list[str]] = {}
    item_sections = {"key_accountabilities", "key_challenges", "key_knowledge_and_experience", "essential_requirements"}
    for block in blocks:
        if isinstance(block, Paragraph):
            text = _paragraph_text(block)
            if not text:
                continue
            if _is_occupation_specific_heading(text):
                current = f"occupation_specific_{_occupation_capability_type(text).lower()}"
                continue
            heading = _heading(text)
            if heading:
                current = heading
                continue
            inline_relationships = re.match(r"^(.*\S)\s+Key relationships\s*$", text, re.IGNORECASE)
            if current in {"key_accountabilities", "key_challenges"} and inline_relationships:
                section_text.setdefault(current, []).append(_clean(inline_relationships.group(1)))
                current = "key_relationships"
                continue
            if current == "key_relationships" and _key(text) in {
                "internal", "external", "ministerial", "minister s office"
            }:
                relationship_group = {
                    "internal": "Internal",
                    "external": "External",
                    "ministerial": "Ministerial",
                    "minister s office": "Ministerial",
                }[_key(text)]
                continue
            if current == "agency_overview":
                continue
            if current:
                current = _append_section_text(section_text, current, text)
        else:
            rows = _table_rows(block)
            table_heading = next((cell for cell in rows[0] if cell), "") if rows else ""
            if _is_occupation_specific_heading(table_heading):
                current = f"occupation_specific_{_occupation_capability_type(table_heading).lower()}"
            if "skills framework for the information age" in _key(table_heading):
                _enrich_sfia_descriptions(block, result)
            if current == "key_relationships":
                _extract_relationships(rows, result, relationship_group)
            if current in {"capabilities_for_the_role", "focus_capabilities", "complementary_capabilities"}:
                _extract_capabilities(rows, current, result)
            if current and current.startswith("occupation_specific_"):
                capability_type = current.removeprefix("occupation_specific_").title()
                _extract_occupation_specific_capabilities(block, result, capability_type)

    if not result["pd_record"]["role_title"]:
        result["pd_record"]["role_title"] = _title_from_core_properties(doc.core_properties.title)

    for key in result["sections"]:
        result["sections"][key] = "\n".join(section_text.get(key, []))
    for section in item_sections:
        target = result[section]
        texts = section_text.get(section, [])
        texts = _recombine_wrapped_items(texts)
        for sequence, text in enumerate(texts, 1):
            target.append({"sequence": sequence, "text": re.sub(r"^\s*[•\-–—\d.)]+\s*", "", text)})

    _validate(result)
    return result


def _title_from_core_properties(value: str | None) -> str:
    title = _clean(value or "")
    title = re.sub(r"^\d+-\d+\s+", "", title)
    if " - " in title:
        title = title.rsplit(" - ", 1)[0]
    return title


def _recombine_wrapped_items(items: list[str]) -> list[str]:
    """Join hard-paragraph wraps where the preceding text is not a complete sentence."""
    combined: list[str] = []
    for item in items:
        text = _clean(item)
        if not text:
            continue
        starts_as_continuation = bool(re.match(r"^[a-z]", text))
        if combined and not re.search(r"[.!?;:]$", combined[-1]) and starts_as_continuation:
            combined[-1] = f"{combined[-1]} {text}"
        else:
            combined.append(text)
    return combined


def _extract_relationships(rows: list[list[str]], result: dict[str, Any], group: str) -> None:
    for row in rows:
        if not any(row):
            continue
        nonempty = [cell for cell in row if cell]
        if len(nonempty) == 1 and _key(nonempty[0]) in {"internal", "external", "ministerial", "minister s office"}:
            group = "Ministerial" if _key(nonempty[0]) in {"ministerial", "minister s office"} else nonempty[0]
        elif len(row) >= 2 and not (_key(row[0]) == "who" and _key(row[1]) == "why"):
            result["key_relationships"].append({"relationship_group": group,
                "sequence": len(result["key_relationships"]) + 1, "who": row[0], "why": row[1]})


def _extract_capabilities(rows: list[list[str]], section: str, result: dict[str, Any]) -> None:
    header = " ".join(_key(cell) for cell in rows[0]) if rows else ""
    inferred_type = (
        "Focus" if section == "focus_capabilities" or "behavioural indicators" in header
        else "Complementary" if section == "complementary_capabilities" or "description" in header
        else None
    )
    for row in rows:
        normalized = [_key(cell) for cell in row]
        matched_key = next(
            (capability for norm in normalized for capability in CAPABILITIES
             if norm == capability or norm.startswith(capability + " ")),
            None,
        )
        name = CAPABILITIES.get(matched_key) if matched_key else None
        level = next((cell for cell, norm in zip(row, normalized) if norm in LEVELS), None)
        if not name or not level:
            continue
        cap_type = inferred_type or ("Focus" if any("focus" in n for n in normalized) else "Complementary")
        record = {"capability_type": cap_type, "sequence": len(result["capabilities"]) + 1,
                  "framework": PUBLIC_SECTOR_FRAMEWORK,
                  "capability_name": name, "level": level}
        if not any(_key(x["capability_name"]) == _key(name) and x["capability_type"] == cap_type for x in result["capabilities"]):
            result["capabilities"].append(record)
            result["capability_field_values"][f"{name} - Type"] = cap_type
            result["capability_field_values"][f"{name} - Level"] = level


def _cell_paragraphs(cell: Any) -> list[str]:
    return [
        text for paragraph in cell.paragraphs
        if (text := _clean("".join(paragraph._p.xpath(".//w:t/text()"))))
    ]


def _infer_occupation_framework(names: list[str]) -> str:
    normalized = {
        re.sub(r"\s+[a-z]{4}$", "", _key(name))
        for name in names
    }
    best_name = "Unidentified occupation-specific framework"
    best_score = 0
    for framework, signatures in OCCUPATION_FRAMEWORK_SIGNATURES.items():
        score = len(normalized & signatures)
        if score > best_score:
            best_name, best_score = framework, score
    return best_name


def _extract_occupation_specific_capabilities(
    table: Table, result: dict[str, Any], capability_type: str
) -> None:
    if not table.rows:
        return
    header_index = next((
        index for index, row in enumerate(table.rows[:3])
        if any(_key(_cell_text(cell)) == "capability name" for cell in row.cells)
        or any("category sub category and skill" in _key(_cell_text(cell)) for cell in row.cells)
    ), None)
    if header_index is None:
        return
    headers = [_key(_cell_text(cell)) for cell in table.rows[header_index].cells]
    is_sfia_assignment = any("category sub category and skill" in value for value in headers)
    if is_sfia_assignment:
        _extract_sfia_assignments(table, header_index, result, capability_type)
        return
    if "capability name" not in headers or "level" not in headers:
        return
    name_index = headers.index("capability name")
    level_index = headers.index("level")
    group_index = next((i for i, value in enumerate(headers) if "group" in value or "set" in value), None)
    description_index = next((i for i, value in enumerate(headers) if value == "description"), None)
    indicators_index = next((i for i, value in enumerate(headers) if "behavioural indicators" in value), None)

    records: list[dict[str, Any]] = []
    for row in table.rows[header_index + 1:]:
        if len(row.cells) <= max(name_index, level_index):
            continue
        name_parts = _cell_paragraphs(row.cells[name_index])
        level = _cell_text(row.cells[level_index])
        if not name_parts or not level:
            continue
        description = ""
        if description_index is not None and description_index < len(row.cells):
            description = _cell_text(row.cells[description_index])
        elif len(name_parts) > 1:
            description = " ".join(name_parts[1:])
        indicators = (
            _cell_paragraphs(row.cells[indicators_index])
            if indicators_index is not None and indicators_index < len(row.cells)
            else []
        )
        group = (
            _cell_text(row.cells[group_index])
            if group_index is not None and group_index < len(row.cells)
            else ""
        )
        name, code = _split_capability_code(name_parts[0])
        records.append({
            "capability_type": capability_type,
            "sequence": len(result["capabilities"]) + len(records) + 1,
            "framework": "",
            "capability_group": group,
            "capability_code": code,
            "capability_name": name,
            "description": description,
            "behavioural_indicators": indicators,
            "level": level,
            "source_text": " | ".join(_cell_text(cell) for cell in row.cells if _cell_text(cell)),
        })
    if not records:
        return
    framework = _infer_occupation_framework([record["capability_name"] for record in records])
    for record in records:
        record["framework"] = framework
    result["capabilities"].extend(records)
    if framework.startswith("Unidentified"):
        result["extraction_issues"].append({
            "issue_type": "Occupation-specific framework not identified",
            "field_or_section": "Capabilities",
            "description": "Occupation-specific capabilities were captured but their framework was not identified",
            "severity": "Low",
        })
    if capability_type == "Unclassified" and not any(
        issue.get("issue_type") == "Occupation-specific capability type not identified"
        for issue in result["extraction_issues"]
    ):
        result["extraction_issues"].append({
            "issue_type": "Occupation-specific capability type not identified",
            "field_or_section": "Capabilities",
            "description": "Occupation-specific capabilities were captured but the source does not identify them as Focus or Complementary",
            "severity": "Low",
        })


def _split_capability_code(name: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*\(([A-Z0-9]{2,8})\)\s*$", name)
    return (_clean(match.group(1)), match.group(2)) if match else (_clean(name), "")


def _extract_sfia_assignments(
    table: Table, header_index: int, result: dict[str, Any], capability_type: str
) -> None:
    records = []
    for row in table.rows[header_index + 1:]:
        if len(row.cells) < 3:
            continue
        skill_parts = _cell_paragraphs(row.cells[-2])
        level_and_code = _cell_text(row.cells[-1])
        if not skill_parts or not level_and_code:
            continue
        level_match = re.search(r"(?i)Level\s+\d+", level_and_code)
        code_match = re.search(r"\b([A-Z]{4})\b", level_and_code)
        records.append({
            "capability_type": capability_type,
            "sequence": len(result["capabilities"]) + len(records) + 1,
            "framework": "Information and Communication Technology (ICT)",
            "capability_group": " | ".join(skill_parts[:-1]),
            "capability_code": code_match.group(1) if code_match else "",
            "capability_name": skill_parts[-1],
            "description": "",
            "behavioural_indicators": [],
            "level": level_match.group(0).title() if level_match else level_and_code,
            "source_text": " | ".join(_cell_text(cell) for cell in row.cells if _cell_text(cell)),
        })
    result["capabilities"].extend(records)
    if records and capability_type == "Unclassified":
        result["extraction_issues"].append({
            "issue_type": "Occupation-specific capability type not identified",
            "field_or_section": "Capabilities",
            "description": "Occupation-specific capabilities were captured but the source does not identify them as Focus or Complementary",
            "severity": "Low",
        })


def _enrich_sfia_descriptions(table: Table, result: dict[str, Any]) -> None:
    if len(table.rows) < 3:
        return
    headers = [_key(_cell_text(cell)) for cell in table.rows[1].cells]
    description_index = next((i for i, value in enumerate(headers) if "level descriptions" in value), None)
    code_index = next((i for i, value in enumerate(headers) if "level and code" in value), None)
    if description_index is None or code_index is None:
        return
    for row in table.rows[2:]:
        if max(description_index, code_index) >= len(row.cells):
            continue
        code_match = re.search(r"\b([A-Z]{4})\b", _cell_text(row.cells[code_index]))
        description = _cell_text(row.cells[description_index])
        if not code_match or not description:
            continue
        for capability in result["capabilities"]:
            if capability.get("capability_code") == code_match.group(1):
                capability["description"] = description
                break


def _validate(result: dict[str, Any]) -> None:
    missing = []
    checks = {
        "Role title": result["pd_record"]["role_title"],
        "Primary purpose": result["sections"]["primary_purpose"],
        "Key accountabilities": result["key_accountabilities"],
        "Key challenges": result["key_challenges"],
        "Key relationships": result["key_relationships"],
        "Essential requirements": result["essential_requirements"],
        "Capabilities": result["capabilities"],
    }
    for field, value in checks.items():
        if not value:
            missing.append(field)
            result["extraction_issues"].append({"issue_type": "Missing mandatory content",
                "field_or_section": field, "description": f"{field} was not extracted", "severity": "High"})
    for relationship in result["key_relationships"]:
        if not relationship["who"] or not relationship["why"]:
            missing_cell = "Who" if not relationship["who"] else "Why"
            result["extraction_issues"].append({
                "issue_type": "Incomplete relationship row",
                "field_or_section": "Key relationships",
                "description": f"Relationship row {relationship['sequence']} has a blank {missing_cell} value",
                "severity": "Medium",
            })
            missing.append(f"Key relationship row {relationship['sequence']} {missing_cell}")
    result["pd_record"]["extraction_warnings"] = [x["description"] for x in result["extraction_issues"]]
    if missing:
        result["pd_record"]["extraction_status"] = "Extraction requires review"
    elif result["extraction_issues"]:
        result["pd_record"]["extraction_status"] = "Extraction complete with warnings"
    else:
        result["pd_record"]["extraction_status"] = "Extraction complete"
