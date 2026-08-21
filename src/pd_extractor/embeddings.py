from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .database import connect_database, initialise_database


DEFAULT_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"


class Embedder(Protocol):
    def encode(self, texts: list[str], **kwargs: object) -> object:
        ...


@dataclass(frozen=True)
class EmbeddingSource:
    source_type: str
    source_id: str
    source_text: str


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _as_float_list(vector: object) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(value) for value in vector]  # type: ignore[arg-type]


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def load_sentence_transformer(model_name: str = DEFAULT_MODEL_NAME) -> Embedder:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "sentence-transformers is not installed. Install project dependencies before generating embeddings."
        ) from error
    return SentenceTransformer(model_name)


def pd_embedding_sources(connection: sqlite3.Connection) -> list[EmbeddingSource]:
    return [
        EmbeddingSource("pd", str(row["position_description_id"]), row["full_text"])
        for row in connection.execute(
            """SELECT position_description_id, full_text
               FROM pd_mapping_texts
               WHERE TRIM(full_text) <> ''
               ORDER BY position_description_id"""
        )
    ]


def framework_embedding_sources(connection: sqlite3.Connection) -> list[EmbeddingSource]:
    rows = connection.execute(
        """SELECT id, code, name, level, main_definition, supp_definition_1,
                  supp_definition_2, exclusions
           FROM active_job_family_entries
           ORDER BY sequence"""
    ).fetchall()
    sources: list[EmbeddingSource] = []
    for row in rows:
        parts = [
            f"Code: {row['code']}",
            f"Name: {row['name']}",
            f"Level: {row['level']}",
        ]
        for label in ("main_definition", "supp_definition_1", "supp_definition_2"):
            if row[label]:
                parts.append(f"{label.replace('_', ' ').title()}: {row[label]}")
        sources.append(EmbeddingSource("framework", str(row["id"]), "\n".join(parts)))
    return sources


def upsert_embeddings(
    connection: sqlite3.Connection,
    sources: list[EmbeddingSource],
    embedder: Embedder,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    batch_size: int = 32,
) -> int:
    written = 0
    for start in range(0, len(sources), batch_size):
        batch = sources[start:start + batch_size]
        texts = [source.source_text for source in batch]
        vectors = embedder.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        rows = []
        for source, vector in zip(batch, vectors):  # type: ignore[union-attr]
            values = _normalise(_as_float_list(vector))
            rows.append((
                source.source_type,
                source.source_id,
                model_name,
                len(values),
                _hash_text(source.source_text),
                source.source_text,
                json.dumps(values, separators=(",", ":")),
            ))
        with connection:
            connection.executemany(
                """INSERT INTO embeddings(
                    source_type, source_id, model_name, embedding_dimension,
                    source_text_hash, source_text, embedding_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_type, source_id, model_name) DO UPDATE SET
                    embedding_dimension = excluded.embedding_dimension,
                    source_text_hash = excluded.source_text_hash,
                    source_text = excluded.source_text,
                    embedding_json = excluded.embedding_json,
                    created_at = CURRENT_TIMESTAMP""",
                rows,
            )
        written += len(rows)
    return written


def generate_embeddings(
    connection: sqlite3.Connection,
    embedder: Embedder,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    include_pds: bool = True,
    include_framework: bool = True,
    batch_size: int = 32,
) -> dict[str, int | str]:
    pd_sources = pd_embedding_sources(connection) if include_pds else []
    framework_sources = framework_embedding_sources(connection) if include_framework else []
    pd_count = upsert_embeddings(
        connection, pd_sources, embedder, model_name=model_name, batch_size=batch_size
    ) if pd_sources else 0
    framework_count = upsert_embeddings(
        connection, framework_sources, embedder, model_name=model_name, batch_size=batch_size
    ) if framework_sources else 0
    return {
        "model_name": model_name,
        "pd_embeddings": pd_count,
        "framework_embeddings": framework_count,
        "total_embeddings": pd_count + framework_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local semantic embeddings for PDs and job family entries")
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--pds-only", action="store_true")
    parser.add_argument("--framework-only", action="store_true")
    args = parser.parse_args()

    connection = connect_database(args.database)
    try:
        initialise_database(connection)
        embedder = load_sentence_transformer(args.model)
        summary = generate_embeddings(
            connection,
            embedder,
            model_name=args.model,
            include_pds=not args.framework_only,
            include_framework=not args.pds_only,
            batch_size=args.batch_size,
        )
    finally:
        connection.close()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
