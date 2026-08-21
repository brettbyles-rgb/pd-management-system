from __future__ import annotations

import argparse
import json
from pathlib import Path

from pd_extractor.config import default_database_path
from pd_extractor.pathways.build import Paths, build_all
from pd_extractor.pathways.unified import build_unified_database


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild pathway outputs from, and refresh, the unified database"
    )
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args()
    database = args.database.resolve()

    pathway_result = build_all(Paths(ROOT, database))
    unified_result = build_unified_database(
        database,
        ROOT / "data" / "generated" / "career_pathways.sqlite3",
        database,
        ROOT / "data" / "qa" / "unified_database_validation.json",
    )
    print(
        json.dumps(
            {"pathway_build": pathway_result, "unified_refresh": unified_result},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
