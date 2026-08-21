from __future__ import annotations

import sqlite3

from .embeddings import DEFAULT_MODEL_NAME, EmbeddingSource, Embedder, upsert_embeddings
from .mapping_text import build_mapping_text_record, upsert_mapping_text


def prepare_pd_intelligence(
    connection: sqlite3.Connection,
    position_description_id: int,
    embedder: Embedder,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, int | str]:
    """Create mapping text and embedding for a single validated/imported PD."""
    record = build_mapping_text_record(connection, position_description_id)
    with connection:
        upsert_mapping_text(connection, record)
    embedded = 0
    if record.full_text.strip():
        embedded = upsert_embeddings(
            connection,
            [EmbeddingSource("pd", str(position_description_id), record.full_text)],
            embedder,
            model_name=model_name,
            batch_size=1,
        )
    return {
        "position_description_id": position_description_id,
        "mapping_texts": 1,
        "pd_embeddings": embedded,
        "model_name": model_name,
    }
