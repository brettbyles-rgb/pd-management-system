from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .database import connect_database, initialise_database
from .embeddings import DEFAULT_MODEL_NAME, Embedder, load_sentence_transformer


@dataclass(frozen=True)
class SimilarRole:
    position_description_id: int
    position_description_no: str
    role_title: str
    source_filename: str
    similarity: float
    primary_mapping_code: str
    primary_mapping_name: str
    primary_mapping_level: str
    mapping_validated: str


def _vector(value: str) -> list[float]:
    return [float(item) for item in json.loads(value)]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _primary_mapping_by_position(connection: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    return {
        int(row["position_description_id"]): row
        for row in connection.execute(
            """SELECT position_description_id, mapping_code, mapping_name,
                      mapping_level, mapping_validated
               FROM active_pd_job_family_mappings
               WHERE mapping_rank = 1 AND position_description_id IS NOT NULL"""
        )
    }


def find_similar_roles(
    connection: sqlite3.Connection,
    position_description_id: int,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    limit: int = 10,
    mapped_only: bool = False,
) -> list[SimilarRole]:
    target = connection.execute(
        """SELECT embedding_json
           FROM embeddings
           WHERE source_type = 'pd' AND source_id = ? AND model_name = ?""",
        (str(position_description_id), model_name),
    ).fetchone()
    if target is None:
        raise KeyError(f"No embedding found for PD id {position_description_id}")
    target_vector = _vector(target["embedding_json"])
    mappings = _primary_mapping_by_position(connection)
    candidates = connection.execute(
        """SELECT e.source_id, e.embedding_json, pd.position_description_no,
                  pd.role_title, pd.source_filename
           FROM embeddings e
           JOIN position_descriptions pd ON pd.id = CAST(e.source_id AS INTEGER)
           WHERE e.source_type = 'pd' AND e.model_name = ? AND e.source_id <> ?
           ORDER BY pd.position_description_no, pd.role_title""",
        (model_name, str(position_description_id)),
    ).fetchall()

    results: list[SimilarRole] = []
    for row in candidates:
        pd_id = int(row["source_id"])
        mapping = mappings.get(pd_id)
        if mapped_only and mapping is None:
            continue
        similarity = cosine_similarity(target_vector, _vector(row["embedding_json"]))
        results.append(
            SimilarRole(
                position_description_id=pd_id,
                position_description_no=row["position_description_no"] or "",
                role_title=row["role_title"] or "",
                source_filename=row["source_filename"] or "",
                similarity=similarity,
                primary_mapping_code=mapping["mapping_code"] if mapping else "",
                primary_mapping_name=mapping["mapping_name"] if mapping else "",
                primary_mapping_level=mapping["mapping_level"] if mapping else "",
                mapping_validated=mapping["mapping_validated"] if mapping else "",
            )
        )
    results.sort(key=lambda item: item.similarity, reverse=True)
    return results[:limit]


def search_roles(
    connection: sqlite3.Connection,
    query: str,
    embedder: Embedder,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    limit: int = 10,
    mapped_only: bool = False,
) -> list[SimilarRole]:
    vector = embedder.encode(
        [query],
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0]
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    query_vector = [float(value) for value in vector]
    mappings = _primary_mapping_by_position(connection)
    candidates = connection.execute(
        """SELECT e.source_id, e.embedding_json, pd.position_description_no,
                  pd.role_title, pd.source_filename
           FROM embeddings e
           JOIN position_descriptions pd ON pd.id = CAST(e.source_id AS INTEGER)
           WHERE e.source_type = 'pd' AND e.model_name = ?
           ORDER BY pd.position_description_no, pd.role_title""",
        (model_name,),
    ).fetchall()
    results: list[SimilarRole] = []
    for row in candidates:
        pd_id = int(row["source_id"])
        mapping = mappings.get(pd_id)
        if mapped_only and mapping is None:
            continue
        results.append(
            SimilarRole(
                position_description_id=pd_id,
                position_description_no=row["position_description_no"] or "",
                role_title=row["role_title"] or "",
                source_filename=row["source_filename"] or "",
                similarity=cosine_similarity(query_vector, _vector(row["embedding_json"])),
                primary_mapping_code=mapping["mapping_code"] if mapping else "",
                primary_mapping_name=mapping["mapping_name"] if mapping else "",
                primary_mapping_level=mapping["mapping_level"] if mapping else "",
                mapping_validated=mapping["mapping_validated"] if mapping else "",
            )
        )
    results.sort(key=lambda item: item.similarity, reverse=True)
    return results[:limit]


def _find_pd_id(connection: sqlite3.Connection, value: str) -> int:
    row = connection.execute(
        """SELECT id FROM position_descriptions
           WHERE CAST(id AS TEXT) = ?
              OR position_description_no = ?
              OR source_filename LIKE ?
           ORDER BY id LIMIT 1""",
        (value, value, f"{value}%"),
    ).fetchone()
    if row is None:
        raise KeyError(f"No position description found for {value}")
    return int(row["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Find semantically similar roles from stored PD embeddings")
    parser.add_argument("pd", nargs="?", help="Database id, position description number, or filename prefix")
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--mapped-only", action="store_true")
    parser.add_argument("--query", help="Free-text role search query")
    args = parser.parse_args()

    connection = connect_database(args.database)
    try:
        initialise_database(connection)
        if args.query:
            embedder = load_sentence_transformer(args.model)
            results = search_roles(
                connection,
                args.query,
                embedder,
                model_name=args.model,
                limit=args.limit,
                mapped_only=args.mapped_only,
            )
        else:
            if not args.pd:
                raise SystemExit("Provide a PD identifier or --query")
            pd_id = _find_pd_id(connection, args.pd)
            results = find_similar_roles(
                connection,
                pd_id,
                model_name=args.model,
                limit=args.limit,
                mapped_only=args.mapped_only,
            )
    finally:
        connection.close()
    print(json.dumps([result.__dict__ for result in results], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
