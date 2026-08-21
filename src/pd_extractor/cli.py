import argparse
import json
from pathlib import Path

from .extractor import extract_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a Word position description to JSON")
    parser.add_argument("document", type=Path)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    if args.document.is_dir():
        output_dir = args.output_dir or Path("output/batch")
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = []
        for document in sorted(args.document.glob("*.docx")):
            result = extract_document(document)
            (output_dir / f"{document.stem}.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            summary.append({
                "source_filename": document.name,
                "role_title": result["pd_record"]["role_title"],
                "extraction_status": result["pd_record"]["extraction_status"],
                "accountabilities": len(result["key_accountabilities"]),
                "challenges": len(result["key_challenges"]),
                "relationships": len(result["key_relationships"]),
                "requirements": len(result["essential_requirements"]),
                "capabilities": len(result["capabilities"]),
                "issues": len(result["extraction_issues"]),
            })
        (output_dir / "_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Extracted {len(summary)} documents to {output_dir}")
        return 0

    result = extract_document(args.document)
    print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False))
    return 0
