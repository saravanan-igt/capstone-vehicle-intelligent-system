"""Embedding models behind one interface: Gemini embeddings, or a deterministic local fallback (no key needed)."""

import logging
import math
import re
import zlib
from collections import Counter
from typing import Any, Literal, Protocol

import numpy as np

log = logging.getLogger(__name__)
Kind = Literal["document", "query"]

STOPWORDS = frozenset(
    "a an and are as at be been but by can do does for from has have how i if in into is it its me my of on or "
    "our so than that the their them then there these this those to was we what when where which who why will "
    "with you your about any tell much many get".split())
SYNONYMS = {"cost": "price", "costs": "price", "priced": "price", "mileage": "efficiency", "color": "colour",
            "colors": "colour", "colours": "colour", "seat": "seats", "seater": "seats", "guarantee": "warranty",
            "servicing": "service", "km/l": "efficiency", "boot": "boot", "trunk": "boot", "gearbox": "transmission",
            "automatic": "automatic", "ev": "electric", "airbag": "airbags", "loans": "loan"}


def terms(text: str) -> list[str]:
    """Lower-cased content words with light normalisation; shared by the local embedder and answer checks."""
    out = []
    for token in re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", text.lower()):
        token = SYNONYMS.get(token, token)
        if token in STOPWORDS or len(token) < 2:
            continue
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss") and not token[:-1].isdigit():
            token = token[:-1]
        out.append(token)
    return out


def normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


class Embedder(Protocol):
    name: str
    model: str
    dim: int

    def embed(self, texts: list[str], kind: Kind) -> np.ndarray: ...

    def state(self) -> dict[str, Any]: ...


class LocalEmbedder:
    """Hashed unigram+bigram TF-IDF. Deterministic, offline, and good enough for a small, well-structured corpus."""

    name = "local"
    model = "hashing-tfidf-v1"

    def __init__(self, dim: int = 4096, idf: list[float] | None = None) -> None:
        self.dim = dim
        self.idf = np.asarray(idf, dtype=np.float32) if idf is not None else np.ones(dim, dtype=np.float32)

    def _features(self, text: str) -> Counter[int]:
        words = terms(text)
        grams = words + [f"{a} {b}" for a, b in zip(words, words[1:])]
        return Counter(zlib.crc32(g.encode()) % self.dim for g in grams)

    def fit(self, texts: list[str]) -> "LocalEmbedder":
        df = np.zeros(self.dim, dtype=np.float32)
        for text in texts:
            for index in self._features(text):
                df[index] += 1
        self.idf = (np.log((1 + len(texts)) / (1 + df)) + 1).astype(np.float32)
        return self

    def embed(self, texts: list[str], kind: Kind) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for index, count in self._features(text).items():
                out[row, index] = (1 + math.log(count)) * self.idf[index]
        return normalise(out)

    def state(self) -> dict[str, Any]:
        return {"dim": self.dim, "idf": [round(float(x), 6) for x in self.idf]}


class EmbeddingUnavailable(RuntimeError):
    pass


class GeminiEmbedder:
    """gemini-embedding-001 with retrieval task types; reduced dimensions are re-normalised for cosine search."""

    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-embedding-001", dim: int = 768,
                 timeout_ms: int = 15000) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str], kind: Kind) -> np.ndarray:
        task = "RETRIEVAL_DOCUMENT" if kind == "document" else "RETRIEVAL_QUERY"
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), 100):
                result = self._client.models.embed_content(
                    model=self.model, contents=texts[start:start + 100],
                    config=self._types.EmbedContentConfig(task_type=task, output_dimensionality=self.dim))
                vectors += [list(e.values or []) for e in result.embeddings or []]
        except Exception as exc:  # network/provider failure: callers fall back to the local index
            log.warning("gemini embedding failed: %s", type(exc).__name__)
            raise EmbeddingUnavailable(type(exc).__name__) from exc
        if len(vectors) != len(texts):
            raise EmbeddingUnavailable("embedding count mismatch")
        return normalise(np.asarray(vectors, dtype=np.float32))

    def state(self) -> dict[str, Any]:
        return {"dim": self.dim}
