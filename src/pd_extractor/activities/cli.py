from __future__ import annotations

import argparse
import json
from pathlib import Path

from .loader import load_from_pd_database
from .stages import (
    export_json,
    import_to_database,
    read_jsonl,
    stage1_extract,
    stage2_vocabulary,
    stage3_assign,
    stage4_qa,
)


def load_vocab(work: Path) -> list[dict]:
    path = work / "2_vocabulary.json"
    if not path.exists():
        raise SystemExit("No vocabulary yet. Run `vocab` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract generic activity profiles from PDs")
    parser.add_argument("cmd", choices=["extract", "vocab", "assign", "qa", "export", "import-db", "all"])
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--work", type=Path, default=Path("work/activities"))
    parser.add_argument("--export-path", type=Path, default=Path("output/activities_export.json"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--clusters", type=int, default=280)
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--shortlist", type=int, default=60)
    parser.add_argument("--sample", type=int, default=60)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)

    if args.cmd == "vocab":
        extracted = read_jsonl(args.work / "1_extracted.jsonl")
        if not extracted:
            raise SystemExit("Nothing extracted yet. Run `extract` first.")
        stage2_vocabulary(extracted, args.work, target_clusters=args.clusters, min_count=args.min_count)
        return 0

    if args.cmd == "import-db":
        import_to_database(args.database, args.export_path)
        return 0

    roles = load_from_pd_database(args.database)
    excluded = sum(len(role.get("excluded_accountabilities", [])) for role in roles)
    print(f"loaded {len(roles)} roles; excluded {excluded} boilerplate accountabilities")

    if args.cmd == "extract":
        stage1_extract(roles, args.work, limit=args.limit)
    elif args.cmd == "assign":
        stage3_assign(roles, load_vocab(args.work), args.work, shortlist=args.shortlist, limit=args.limit)
    elif args.cmd == "qa":
        stage4_qa(roles, load_vocab(args.work), read_jsonl(args.work / "3_assigned.jsonl"), args.work, sample=args.sample)
    elif args.cmd == "export":
        export_json(roles, load_vocab(args.work), read_jsonl(args.work / "3_assigned.jsonl"), args.export_path)
    elif args.cmd == "all":
        extracted = stage1_extract(roles, args.work, limit=args.limit)
        vocab = stage2_vocabulary(extracted, args.work, target_clusters=args.clusters, min_count=args.min_count)
        assigned = stage3_assign(roles, vocab, args.work, shortlist=args.shortlist, limit=args.limit)
        stage4_qa(roles, vocab, assigned, args.work, sample=args.sample)
        export_json(roles, vocab, assigned, args.export_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
