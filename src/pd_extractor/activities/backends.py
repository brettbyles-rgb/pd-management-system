from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

import numpy as np


class LLMBackend(Protocol):
    name: str

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str: ...


class EmbeddingBackend(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class Cache:
    def __init__(self, path: str | Path = "work/activity-cache"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def _key(self, *parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:32]

    def get(self, *parts: str) -> str | None:
        path = self.path / f"{self._key(*parts)}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put(self, value: str, *parts: str) -> None:
        path = self.path / f"{self._key(*parts)}.txt"
        with self.lock:
            path.write_text(value, encoding="utf-8")


CACHE = Cache()


class BaseLLM:
    name = "base"
    max_workers = 8

    def _raw(self, system: str, user: str, max_tokens: int) -> str:
        raise NotImplementedError

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        hit = CACHE.get(self.name, system, user)
        if hit is not None:
            return hit
        delay = 2.0
        for attempt in range(6):
            try:
                out = self._raw(system, user, max_tokens)
                if not out.strip():
                    raise RuntimeError("LLM returned an empty response")
                CACHE.put(out, self.name, system, user)
                return out
            except Exception as exc:
                if attempt == 5:
                    raise
                if "rate" in str(exc).lower() or "429" in str(exc):
                    delay = min(delay * 2, 60)
                time.sleep(delay)
                delay = min(delay * 1.6, 60)
        raise RuntimeError("unreachable")

    def complete_many(self, jobs: list[tuple[str, str]], max_tokens: int = 1500, progress=None) -> list[str]:
        out: list[str | None] = [None] * len(jobs)
        done = [0]
        lock = threading.Lock()

        def work(i: int) -> None:
            system, user = jobs[i]
            out[i] = self.complete(system, user, max_tokens)
            with lock:
                done[0] += 1
                if progress and (done[0] % 25 == 0 or done[0] == len(jobs)):
                    progress(done[0], len(jobs))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            list(executor.map(work, range(len(jobs))))
        return out  # type: ignore[return-value]


class OpenAICompatible(BaseLLM):
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None, max_workers: int = 8):
        from openai import OpenAI

        self.model = model or os.environ.get("LLM_MODEL", "gpt-4.1-mini")
        self.client = OpenAI(
            base_url=base_url or os.environ.get("LLM_BASE_URL") or None,
            api_key=api_key or os.environ.get("LLM_API_KEY", "not-needed"),
        )
        self.name = f"openai-compatible:{self.model}"
        self.max_workers = max_workers

    def _raw(self, system: str, user: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


class KimiK3(BaseLLM):
    def __init__(self, model: str | None = None, max_workers: int = 4):
        from openai import OpenAI

        self.model = model or os.environ.get("LLM_MODEL", "kimi-k3")
        self.client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.moonshot.ai/v1"),
            api_key=os.environ.get("MOONSHOT_API_KEY") or os.environ.get("LLM_API_KEY"),
        )
        self.name = f"kimi:{self.model}"
        self.max_workers = max_workers

    def _raw(self, system: str, user: str, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max_tokens,
            reasoning_effort=os.environ.get("KIMI_REASONING_EFFORT", "low"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


class FileHandoff(BaseLLM):
    name = "file-handoff"

    def __init__(self, path: str | Path = "work/activity-handoff"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.answers: dict[str, str] = {}
        answers = self.path / "answers.jsonl"
        if answers.exists():
            for line in answers.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    self.answers[item["id"]] = item["text"]

    def _raw(self, system: str, user: str, max_tokens: int) -> str:
        request_id = hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()[:16]
        if request_id in self.answers:
            return self.answers[request_id]
        pending = {"id": request_id, "system": system, "user": user}
        with (self.path / "pending.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(pending, ensure_ascii=False) + "\n")
        raise RuntimeError(f"No handoff answer for {request_id}; wrote prompt to {self.path / 'pending.jsonl'}")


class TfidfSVD:
    name = "tfidf-svd"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, stop_words="english")
        matrix = vectorizer.fit_transform(texts)
        dim = min(self.dim, max(2, min(matrix.shape) - 1))
        vectors = TruncatedSVD(n_components=dim, random_state=0).fit_transform(matrix)
        vectors = np.asarray(vectors, dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
        return vectors


def get_llm(role: str = "extract") -> LLMBackend:
    backend = os.environ.get("ACTIVITY_LLM_BACKEND", "kimi").lower()
    if backend == "handoff":
        return FileHandoff()
    if backend == "openai":
        model = os.environ.get("LLM_MODEL_FAST" if role == "extract" else "LLM_MODEL_SMART")
        return OpenAICompatible(model=model)
    if backend == "kimi":
        return KimiK3(model=os.environ.get("LLM_MODEL", "kimi-k3"))
    raise ValueError(f"Unknown ACTIVITY_LLM_BACKEND {backend!r}")


def get_embedder() -> EmbeddingBackend:
    return TfidfSVD()
