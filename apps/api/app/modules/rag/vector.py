from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class FastEmbeddingProvider:
    def __init__(self, *, model_name: str, cache_dir: str) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=self.cache_dir,
                )
            vectors = list(self._model.embed(texts))
        return [[float(value) for value in vector] for vector in vectors]


def normalize_vector(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(float(value) * float(value) for value in vector))
    if norm <= 0:
        return [0.0 for _ in vector]
    return [float(value) / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(float(a) * float(b) for a, b in zip(left, right, strict=True))


def combine_hybrid_scores(
    lexical_scores: Sequence[float],
    vector_scores: Sequence[float],
    *,
    vector_weight: float,
) -> list[float]:
    if len(lexical_scores) != len(vector_scores):
        raise ValueError("lexical_scores and vector_scores must have the same length")
    weight = min(1.0, max(0.0, float(vector_weight)))
    combined: list[float] = []
    for lexical, vector in zip(lexical_scores, vector_scores, strict=True):
        normalized_lexical = max(0.0, float(lexical)) / (max(0.0, float(lexical)) + 2.0)
        normalized_vector = max(0.0, min(1.0, float(vector)))
        combined.append(round((1.0 - weight) * normalized_lexical + weight * normalized_vector, 6))
    return combined