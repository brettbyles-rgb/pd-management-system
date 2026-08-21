from __future__ import annotations

import csv
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import prompts
from .backends import get_embedder, get_llm


def _p(*parts: object) -> None:
    print(*parts, file=sys.stderr, flush=True)


def parse_json(text: str) -> dict:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?|```$", "", stripped, flags=re.M).strip()
    try:
        return json.loads(stripped)
    except Exception:
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(stripped[start : end + 1])
        except Exception:
            pass
    return {}


def read_jsonl(path: str | Path) -> dict[str, dict]:
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            out[str(item["pd_id"])] = item
    return out


def append_jsonl(path: str | Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _context(role: dict) -> str:
    bits = [role.get("classification"), role.get("job_family"), role.get("sub_family")]
    context = " | ".join(str(bit) for bit in bits if bit)
    out = f"Context: {context}" if context else ""
    if role.get("purpose"):
        out += f"\nPurpose: {str(role['purpose'])[:400]}"
    return out


def _numbered(items: list[str]) -> str:
    return "\n".join(f"[{index}] {item}" for index, item in enumerate(items))


def _extract_activities(text: str) -> list[dict]:
    activities = parse_json(text).get("activities") or []
    clean = []
    for activity in activities:
        match_label = str(activity.get("match_label") or "").strip().lower()
        plain_label = str(activity.get("plain_label") or "").strip()
        if match_label:
            clean.append({"match_label": match_label, "plain_label": plain_label or match_label, "from": activity.get("from") or []})
    return clean


def _assignment_ids(text: str, valid: set[str]) -> tuple[list[str], list[str]]:
    parsed = parse_json(text)
    ids = [activity_id for activity_id in (parsed.get("activity_ids") or []) if activity_id in valid]
    gaps = [str(gap).strip() for gap in (parsed.get("gaps") or []) if str(gap).strip()]
    return ids, gaps


def stage1_extract(roles: list[dict], work: Path, limit: int | None = None) -> dict[str, dict]:
    out_path = work / "1_extracted.jsonl"
    done = read_jsonl(out_path)
    todo = [role for role in roles if str(role["pd_id"]) not in done]
    if limit:
        todo = todo[:limit]
    _p(f"[1] extract: {len(done)} done, {len(todo)} to do")
    if not todo:
        return read_jsonl(out_path)

    llm = get_llm("extract")
    jobs = [
        (
            prompts.EXTRACT_SYSTEM,
            prompts.EXTRACT_USER.format(title=role["title"], context=_context(role), numbered=_numbered(role["accountabilities"])),
        )
        for role in todo
    ]
    extract_max_tokens = 4000
    texts = llm.complete_many(jobs, max_tokens=extract_max_tokens, progress=lambda done_count, total: _p(f"    {done_count}/{total}"))
    bad = 0
    for role, job, text in zip(todo, jobs, texts):
        clean = _extract_activities(text)
        retry_count = 0
        while not clean and retry_count < 2:
            retry_count += 1
            system, user = job
            retry_user = (
                f"{user}\n\n"
                "Your previous response was blank or invalid JSON. Return one complete, valid JSON object only, "
                "using exactly this shape: {\"activities\":[{\"from\":[0],\"match_label\":\"...\",\"plain_label\":\"...\"}]}"
            )
            text = llm.complete(system, retry_user, max_tokens=extract_max_tokens)
            clean = _extract_activities(text)
        if not clean:
            bad += 1
        append_jsonl(
            out_path,
            {
                "pd_id": str(role["pd_id"]),
                "position_description_id": role.get("position_description_id"),
                "position_description_no": role.get("position_description_no"),
                "title": role["title"],
                "source_accountability_count": role.get("source_accountability_count", len(role["accountabilities"])),
                "excluded_accountabilities": role.get("excluded_accountabilities", []),
                "retry_count": retry_count,
                "activities": clean,
            },
        )
    if bad:
        _p(f"[1] warning: {bad} roles returned nothing parseable")
    return read_jsonl(out_path)


def stage2_vocabulary(extracted: dict[str, dict], work: Path, target_clusters: int = 280, min_count: int = 1) -> list[dict]:
    counts = Counter()
    plain_of = defaultdict(Counter)
    for record in extracted.values():
        for activity in record["activities"]:
            counts[activity["match_label"]] += 1
            plain_of[activity["match_label"]][activity["plain_label"]] += 1
    phrases = [phrase for phrase, count in counts.items() if count >= min_count]
    _p(f"[2] {len(counts)} distinct raw phrases; {len(phrases)} seen >= {min_count}")
    if len(phrases) < 2:
        raise RuntimeError("Not enough extracted phrases to build a vocabulary")

    embedder = get_embedder()
    vectors = embedder.embed(phrases)
    from sklearn.cluster import AgglomerativeClustering

    cluster_count = min(target_clusters, max(2, len(phrases) // 3))
    labels = AgglomerativeClustering(n_clusters=cluster_count, metric="cosine", linkage="average").fit_predict(vectors)
    groups: dict[int, list[str]] = defaultdict(list)
    for phrase, label in zip(phrases, labels):
        groups[int(label)].append(phrase)
    _p(f"[2] {cluster_count} clusters; largest {max(len(group) for group in groups.values())}")

    llm = get_llm("name")
    keys = sorted(groups, key=lambda key: -len(groups[key]))
    jobs = []
    for key in keys:
        members = sorted(groups[key], key=lambda phrase: -counts[phrase])[:40]
        listing = "\n".join(f"- {phrase} (x{counts[phrase]})" for phrase in members)
        jobs.append((prompts.CLUSTER_SYSTEM, prompts.CLUSTER_USER.format(n=len(groups[key]), phrases=listing)))
    texts = llm.complete_many(jobs, max_tokens=800, progress=lambda done_count, total: _p(f"    {done_count}/{total}"))

    vocab = []
    member_map = {}
    seen = set()
    for key, text in zip(keys, texts):
        got = parse_json(text).get("activities") or []
        if not got:
            top = max(groups[key], key=lambda phrase: counts[phrase])
            got = [{"match_label": top, "plain_label": plain_of[top].most_common(1)[0][0], "discriminating": True}]
        for activity in got:
            match_label = str(activity.get("match_label") or "").strip().lower()
            if not match_label or match_label in seen:
                continue
            raw_phrases = groups[key]
            raw_count = sum(counts[phrase] for phrase in raw_phrases)
            singleton_count = sum(1 for phrase in raw_phrases if counts[phrase] == 1)
            rare_count = sum(1 for phrase in raw_phrases if counts[phrase] <= 2)
            seen.add(match_label)
            activity_id = f"a{len(vocab):03d}"
            vocab.append(
                {
                    "id": activity_id,
                    "match_label": match_label,
                    "plain_label": str(activity.get("plain_label") or match_label).strip(),
                    "discriminating": bool(activity.get("discriminating", True)),
                    "cluster": key,
                    "raw_count": raw_count,
                    "raw_phrase_count": len(raw_phrases),
                    "singleton_phrase_count": singleton_count,
                    "rare_phrase_count": rare_count,
                    "has_singleton_member": singleton_count > 0,
                    "min_member_count": min(counts[phrase] for phrase in raw_phrases),
                    "max_member_count": max(counts[phrase] for phrase in raw_phrases),
                }
            )
            member_map[activity_id] = raw_phrases
    (work / "2_vocabulary.json").write_text(json.dumps(vocab, indent=1, ensure_ascii=False), encoding="utf-8")
    (work / "2_cluster_members.json").write_text(json.dumps(member_map, indent=1, ensure_ascii=False), encoding="utf-8")
    _p(f"[2] vocabulary: {len(vocab)} activities")
    return vocab


def stage3_assign(roles: list[dict], vocab: list[dict], work: Path, shortlist: int = 60, limit: int | None = None) -> dict[str, dict]:
    out_path = work / "3_assigned.jsonl"
    done = read_jsonl(out_path)
    todo = [role for role in roles if str(role["pd_id"]) not in done]
    if limit:
        todo = todo[:limit]
    _p(f"[3] assign: {len(done)} done, {len(todo)} to do")
    if not todo:
        return read_jsonl(out_path)

    embedder = get_embedder()
    vocab_text = [f"{item['match_label']} - {item['plain_label']}" for item in vocab]
    role_text = [" ".join(role["accountabilities"]) for role in todo]
    vectors = embedder.embed(vocab_text + role_text)
    vocab_vectors, role_vectors = vectors[: len(vocab_text)], vectors[len(vocab_text) :]
    sims = role_vectors @ vocab_vectors.T

    llm = get_llm("assign")
    valid = {item["id"] for item in vocab}
    shortlists = []
    for row_index, role in enumerate(todo):
        indexes = np.argsort(-sims[row_index])[:shortlist]
        selected = [vocab[index] for index in indexes]
        shortlists.append(selected)

    for index, (role, selected) in enumerate(zip(todo, shortlists), start=1):
        listing = "\n".join(f"{item['id']} {item['match_label']}" for item in selected)
        user = prompts.ASSIGN_USER.format(title=role["title"], context=_context(role), numbered=_numbered(role["accountabilities"]), vocab=listing)
        text = ""
        retry_count = 0
        gaps: list[str] = []
        ids: list[str] = []
        while retry_count < 3:
            retry_user = user
            if retry_count:
                retry_user = (
                    f"{user}\n\n"
                    "Your previous response was blank or invalid JSON. Return one complete, valid JSON object only, "
                    "using exactly this shape: {\"activity_ids\":[\"a001\"],\"gaps\":[]}"
                )
            try:
                text = llm.complete(prompts.ASSIGN_SYSTEM, retry_user, max_tokens=1200)
            except Exception:
                retry_count += 1
                if retry_count >= 3:
                    break
                continue
            ids, gaps = _assignment_ids(text, valid)
            if ids:
                break
            retry_count += 1
        if not ids:
            ids = [item["id"] for item in selected[:8]]
        append_jsonl(
            out_path,
            {
                "pd_id": str(role["pd_id"]),
                "position_description_id": role.get("position_description_id"),
                "position_description_no": role.get("position_description_no"),
                "title": role["title"],
                "activity_ids": _unique_preserve_order(ids)[:14],
                "gaps": gaps,
                "retry_count": retry_count,
                "fallback_used": not bool(_assignment_ids(text, valid)[0]) if text else True,
            },
        )
        if index % 25 == 0 or index == len(todo):
            _p(f"    {index}/{len(todo)}")
    return read_jsonl(out_path)


def stage4_qa(roles: list[dict], vocab: list[dict], assigned: dict[str, dict], work: Path, sample: int = 60) -> dict:
    by_id = {item["id"]: item for item in vocab}
    profiles = {pd_id: set(record["activity_ids"]) for pd_id, record in assigned.items()}
    count = len(profiles)
    signatures = Counter(frozenset(items) for items in profiles.values())
    document_frequency = Counter()
    for items in profiles.values():
        document_frequency.update(items)
    sizes = [len(items) for items in profiles.values()]
    report = {
        "roles": count,
        "vocabulary": len(vocab),
        "distinct_profiles": len(signatures),
        "distinct_pct": round(len(signatures) / count * 100, 1) if count else 0,
        "roles_sharing_a_profile": sum(total for _, total in signatures.items() if total > 1),
        "activities_per_role_median": int(np.median(sizes)) if sizes else 0,
        "activities_never_used": sum(1 for item in vocab if document_frequency[item["id"]] == 0),
        "activities_in_over_60pct_of_roles": sum(1 for _, freq in document_frequency.items() if freq > 0.60 * count),
    }
    report["verdict"] = "USABLE" if count and report["distinct_pct"] >= 70 else "TOO COARSE"
    print(json.dumps(report, indent=1))

    by_pd = {str(role["pd_id"]): role for role in roles}
    random.seed(7)
    picked = random.sample(list(assigned), min(sample, len(assigned)))
    with (work / "4_review_sample.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pd_id", "position_description_no", "title", "classification", "activities_plain", "accountabilities", "correct? (y/n)", "notes"])
        for pd_id in picked:
            role = by_pd.get(str(pd_id), {})
            labels = " | ".join(by_id[activity_id]["plain_label"] for activity_id in assigned[pd_id]["activity_ids"] if activity_id in by_id)
            writer.writerow([pd_id, role.get("position_description_no", ""), assigned[pd_id]["title"], role.get("classification", ""), labels, " ".join(role.get("accountabilities", []))[:1200], "", ""])
    (work / "4_qa_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    _p(f"wrote {work / '4_review_sample.csv'}")
    return report


def export_json(roles: list[dict], vocab: list[dict], assigned: dict[str, dict], path: str | Path) -> dict:
    by_id = {item["id"]: item for item in vocab}
    frequencies = Counter()
    for record in assigned.values():
        frequencies.update(_unique_preserve_order(record["activity_ids"]))
    total = max(1, len(assigned))
    output = {
        "vocabulary": [{**item, "roles": frequencies[item["id"]], "share": round(frequencies[item["id"]] / total, 4)} for item in vocab],
        "roles": [
            {
                "pd_id": pd_id,
                "position_description_id": record.get("position_description_id"),
                "position_description_no": record.get("position_description_no"),
                "title": record["title"],
                "activity_ids": _unique_preserve_order(record["activity_ids"]),
                "activities_plain": [
                    by_id[activity_id]["plain_label"]
                    for activity_id in _unique_preserve_order(record["activity_ids"])
                    if activity_id in by_id
                ],
                "gaps": record.get("gaps") or [],
            }
            for pd_id, record in assigned.items()
        ],
    }
    Path(path).write_text(json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8")
    _p(f"wrote {path}")
    return output


def import_to_database(database: str | Path, export_path: str | Path) -> None:
    data = json.loads(Path(export_path).read_text(encoding="utf-8"))
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    with connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS activity_definitions (
                id TEXT PRIMARY KEY,
                match_label TEXT NOT NULL UNIQUE,
                plain_label TEXT NOT NULL,
                discriminating INTEGER NOT NULL,
                cluster_id INTEGER,
                raw_count INTEGER NOT NULL DEFAULT 0,
                role_count INTEGER NOT NULL DEFAULT 0,
                role_share REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS position_description_activities (
                position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
                activity_id TEXT NOT NULL REFERENCES activity_definitions(id) ON DELETE CASCADE,
                activity_rank INTEGER NOT NULL CHECK(activity_rank BETWEEN 1 AND 14),
                source TEXT NOT NULL DEFAULT 'activity_pipeline',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(position_description_id, activity_id)
            );
            CREATE TABLE IF NOT EXISTS activity_assignment_gaps (
                id INTEGER PRIMARY KEY,
                position_description_id INTEGER NOT NULL REFERENCES position_descriptions(id) ON DELETE CASCADE,
                gap_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS activity_cluster_members (
                activity_id TEXT NOT NULL REFERENCES activity_definitions(id) ON DELETE CASCADE,
                raw_phrase TEXT NOT NULL,
                PRIMARY KEY(activity_id, raw_phrase)
            );
            CREATE INDEX IF NOT EXISTS idx_position_description_activities_pd
                ON position_description_activities(position_description_id, activity_rank);
            CREATE INDEX IF NOT EXISTS idx_position_description_activities_activity
                ON position_description_activities(activity_id);
            """
        )
        connection.execute("DELETE FROM activity_cluster_members")
        connection.execute("DELETE FROM activity_assignment_gaps")
        connection.execute("DELETE FROM position_description_activities")
        connection.execute("DELETE FROM activity_definitions")
        connection.executemany(
            """INSERT INTO activity_definitions(
                id, match_label, plain_label, discriminating, cluster_id,
                raw_count, role_count, role_share
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    item["id"],
                    item["match_label"],
                    item["plain_label"],
                    1 if item.get("discriminating", True) else 0,
                    item.get("cluster"),
                    int(item.get("raw_count") or 0),
                    int(item.get("roles") or 0),
                    float(item.get("share") or 0),
                )
                for item in data["vocabulary"]
            ],
        )
        for role in data["roles"]:
            position_id = role.get("position_description_id")
            if position_id is None:
                continue
            connection.executemany(
                """INSERT INTO position_description_activities(
                    position_description_id, activity_id, activity_rank
                ) VALUES (?, ?, ?)""",
                [(position_id, activity_id, rank) for rank, activity_id in enumerate(_unique_preserve_order(role["activity_ids"]), start=1)],
            )
            connection.executemany(
                "INSERT INTO activity_assignment_gaps(position_description_id, gap_text) VALUES (?, ?)",
                [(position_id, gap) for gap in role.get("gaps") or [] if str(gap).strip()],
            )
    connection.close()
    _p(f"imported activities into {database}")
