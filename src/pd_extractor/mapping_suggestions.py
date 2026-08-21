from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .database import connect_database, initialise_database
from .embeddings import DEFAULT_MODEL_NAME, Embedder, load_sentence_transformer
from .similarity import SimilarRole, _find_pd_id, _vector, cosine_similarity, find_similar_roles, search_roles


@dataclass(frozen=True)
class MappingEvidence:
    position_description_id: int
    position_description_no: str
    role_title: str
    similarity: float
    mapping_validated: str


@dataclass
class MappingSuggestion:
    mapping_code: str
    mapping_name: str
    mapping_level: str
    weighted_score: float
    evidence_count: int
    validated_evidence_count: int
    best_similarity: float
    confidence: str
    average_top_3_similarity: float = 0.0
    validation_signal: float = 0.0
    evidence: list[MappingEvidence] = field(default_factory=list)
    hierarchy: list[dict[str, str]] = field(default_factory=list)


def _is_validated(value: str) -> bool:
    return value.strip().lower() in {"yes", "validated", "true", "y"}


def _confidence(
    *,
    best_similarity: float,
    evidence_count: int,
    validated_evidence_count: int,
    top_score: float,
    second_score: float,
) -> str:
    if evidence_count >= 3 and validated_evidence_count >= 2 and best_similarity >= 0.85 and top_score >= second_score * 1.03:
        return "High"
    if evidence_count >= 2 and best_similarity >= 0.60:
        return "Medium"
    return "Low"


def _scored_evidence(
    evidence: list[MappingEvidence],
    *,
    validated_evidence_count: int,
) -> tuple[float, float, float, float]:
    """Return final score plus components for transparent ranking.

    The ranking intentionally avoids a raw sum because large job families or
    common mappings can otherwise win simply by having more examples in the
    corpus. Strength and consistency of the best evidence drive the score;
    volume is capped.
    """
    if not evidence:
        return 0.0, 0.0, 0.0, 0.0
    similarities = sorted((item.similarity for item in evidence), reverse=True)
    best_match = similarities[0]
    average_top_3 = sum(similarities[:3]) / min(3, len(similarities))
    validation_signal = validated_evidence_count / len(evidence)
    evidence_count_signal = max(0, min(len(evidence), 3) - 1) / 2
    score = (
        0.25 * best_match
        + 0.60 * average_top_3
        + 0.03 * validation_signal
        + 0.12 * evidence_count_signal
    )
    return score, best_match, average_top_3, validation_signal


def suggest_mappings_from_similar_roles(
    similar_roles: list[SimilarRole],
    *,
    limit: int = 5,
) -> list[MappingSuggestion]:
    grouped: dict[tuple[str, str, str], MappingSuggestion] = {}
    for role in similar_roles:
        if not role.primary_mapping_code:
            continue
        key = (
            role.primary_mapping_code,
            role.primary_mapping_name,
            role.primary_mapping_level,
        )
        if key not in grouped:
            grouped[key] = MappingSuggestion(
                mapping_code=role.primary_mapping_code,
                mapping_name=role.primary_mapping_name,
                mapping_level=role.primary_mapping_level,
                weighted_score=0.0,
                evidence_count=0,
                validated_evidence_count=0,
                best_similarity=0.0,
                confidence="Low",
            )
        suggestion = grouped[key]
        validated_multiplier = 1.15 if _is_validated(role.mapping_validated) else 1.0
        suggestion.weighted_score += role.similarity * validated_multiplier
        suggestion.evidence_count += 1
        suggestion.validated_evidence_count += 1 if _is_validated(role.mapping_validated) else 0
        suggestion.best_similarity = max(suggestion.best_similarity, role.similarity)
        suggestion.evidence.append(
            MappingEvidence(
                position_description_id=role.position_description_id,
                position_description_no=role.position_description_no,
                role_title=role.role_title,
                similarity=role.similarity,
                mapping_validated=role.mapping_validated,
            )
        )

    for suggestion in grouped.values():
        suggestion.evidence.sort(key=lambda item: item.similarity, reverse=True)
        (
            suggestion.weighted_score,
            suggestion.best_similarity,
            suggestion.average_top_3_similarity,
            suggestion.validation_signal,
        ) = _scored_evidence(
            suggestion.evidence,
            validated_evidence_count=suggestion.validated_evidence_count,
        )

    suggestions = sorted(grouped.values(), key=lambda item: item.weighted_score, reverse=True)
    for index, suggestion in enumerate(suggestions):
        second_score = suggestions[1].weighted_score if index == 0 and len(suggestions) > 1 else 0.0
        suggestion.confidence = _confidence(
            best_similarity=suggestion.best_similarity,
            evidence_count=suggestion.evidence_count,
            validated_evidence_count=suggestion.validated_evidence_count,
            top_score=suggestion.weighted_score,
            second_score=second_score,
        )
        suggestion.evidence = suggestion.evidence[:10]
    return suggestions[:limit]


def _mapping_hierarchy(connection: sqlite3.Connection, mapping_code: str) -> list[dict[str, str]]:
    if not mapping_code:
        return []
    entries = {
        row["code"]: {
            "code": row["code"] or "",
            "name": row["name"] or "",
            "level": row["level"] or "",
            "parent_code": row["parent_code"] or "",
        }
        for row in connection.execute(
            """SELECT code, name, level, parent_code
               FROM active_job_family_entries"""
        )
    }
    lineage = []
    seen = set()
    current = entries.get(mapping_code)
    while current and current["code"] not in seen:
        seen.add(current["code"])
        lineage.append({
            "code": current["code"],
            "name": current["name"],
            "level": current["level"],
        })
        parent_code = current["parent_code"]
        current = entries.get(parent_code) if parent_code else None
    return list(reversed(lineage))


def enrich_mapping_suggestion_hierarchies(
    connection: sqlite3.Connection,
    suggestions: list[MappingSuggestion],
) -> list[MappingSuggestion]:
    for suggestion in suggestions:
        suggestion.hierarchy = _mapping_hierarchy(connection, suggestion.mapping_code)
    return suggestions


def _framework_entries_by_id(connection: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    return {
        int(row["id"]): row
        for row in connection.execute(
            """SELECT id, code, name, level, parent_code,
                      main_definition, supp_definition_1,
                      supp_definition_2, exclusions
               FROM active_job_family_entries"""
        )
    }


def _framework_similarity_scores(
    connection: sqlite3.Connection,
    target_vector: list[float],
    *,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, dict[str, object]]:
    entries = _framework_entries_by_id(connection)
    rows = connection.execute(
        """SELECT source_id, embedding_json
           FROM embeddings
           WHERE source_type = 'framework' AND model_name = ?""",
        (model_name,),
    ).fetchall()
    scores: dict[str, dict[str, object]] = {}
    for row in rows:
        entry = entries.get(int(row["source_id"]))
        if entry is None:
            continue
        score = cosine_similarity(target_vector, _vector(row["embedding_json"]))
        scores[entry["code"]] = {
            "code": entry["code"] or "",
            "name": entry["name"] or "",
            "level": entry["level"] or "",
            "parent_code": entry["parent_code"] or "",
            "main_definition": entry["main_definition"] or "",
            "supp_definition_1": entry["supp_definition_1"] or "",
            "supp_definition_2": entry["supp_definition_2"] or "",
            "exclusions": entry["exclusions"] or "",
            "framework_similarity": round(score, 6),
        }
    return scores


def framework_similarity_scores_for_pd(
    connection: sqlite3.Connection,
    position_description_id: int,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, dict[str, object]]:
    target = connection.execute(
        """SELECT embedding_json
           FROM embeddings
           WHERE source_type = 'pd' AND source_id = ? AND model_name = ?""",
        (str(position_description_id), model_name),
    ).fetchone()
    if target is None:
        return {}
    return _framework_similarity_scores(
        connection,
        _vector(target["embedding_json"]),
        model_name=model_name,
    )


def framework_similarity_scores_for_query(
    connection: sqlite3.Connection,
    query: str,
    embedder: Embedder,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, dict[str, object]]:
    vector = embedder.encode(
        [query],
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0]
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    query_vector = [float(value) for value in vector]
    return _framework_similarity_scores(connection, query_vector, model_name=model_name)


def suggest_mappings_for_pd(
    connection: sqlite3.Connection,
    position_description_id: int,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    neighbour_limit: int = 25,
    suggestion_limit: int = 5,
    mapped_only: bool = True,
) -> list[MappingSuggestion]:
    similar_roles = find_similar_roles(
        connection,
        position_description_id,
        model_name=model_name,
        limit=neighbour_limit,
        mapped_only=mapped_only,
    )
    return enrich_mapping_suggestion_hierarchies(
        connection,
        suggest_mappings_from_similar_roles(similar_roles, limit=suggestion_limit),
    )


def suggest_mappings_for_query(
    connection: sqlite3.Connection,
    query: str,
    embedder: Embedder,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    neighbour_limit: int = 25,
    suggestion_limit: int = 5,
    mapped_only: bool = True,
) -> list[MappingSuggestion]:
    similar_roles = search_roles(
        connection,
        query,
        embedder,
        model_name=model_name,
        limit=neighbour_limit,
        mapped_only=mapped_only,
    )
    return enrich_mapping_suggestion_hierarchies(
        connection,
        suggest_mappings_from_similar_roles(similar_roles, limit=suggestion_limit),
    )


def _to_jsonable(suggestions: list[MappingSuggestion]) -> list[dict[str, object]]:
    return [
        {
            "mapping_code": suggestion.mapping_code,
            "mapping_name": suggestion.mapping_name,
            "mapping_level": suggestion.mapping_level,
            "weighted_score": round(suggestion.weighted_score, 6),
            "evidence_count": suggestion.evidence_count,
            "validated_evidence_count": suggestion.validated_evidence_count,
            "best_similarity": round(suggestion.best_similarity, 6),
            "average_top_3_similarity": round(suggestion.average_top_3_similarity, 6),
            "validation_signal": round(suggestion.validation_signal, 6),
            "confidence": suggestion.confidence,
            "hierarchy": suggestion.hierarchy,
            "evidence": [
                {
                    "position_description_id": item.position_description_id,
                    "position_description_no": item.position_description_no,
                    "role_title": item.role_title,
                    "similarity": round(item.similarity, 6),
                    "mapping_validated": item.mapping_validated,
                }
                for item in suggestion.evidence
            ],
        }
        for suggestion in suggestions
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest job family mappings from similar mapped PDs")
    parser.add_argument("pd", nargs="?", help="Database id, position description number, or filename prefix")
    parser.add_argument("--query", help="Free-text role search query")
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--neighbours", type=int, default=25)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    connection = connect_database(args.database)
    try:
        initialise_database(connection)
        if args.query:
            embedder = load_sentence_transformer(args.model)
            suggestions = suggest_mappings_for_query(
                connection,
                args.query,
                embedder,
                model_name=args.model,
                neighbour_limit=args.neighbours,
                suggestion_limit=args.limit,
            )
        else:
            if not args.pd:
                raise SystemExit("Provide a PD identifier or --query")
            suggestions = suggest_mappings_for_pd(
                connection,
                _find_pd_id(connection, args.pd),
                model_name=args.model,
                neighbour_limit=args.neighbours,
                suggestion_limit=args.limit,
            )
    finally:
        connection.close()
    print(json.dumps(_to_jsonable(suggestions), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
