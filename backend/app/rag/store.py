"""A small persistent vector store: normalised float32 matrix + chunk metadata, cosine search with filters."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.rag.chunking import Chunk


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float

    def to_dict(self, with_text: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.chunk.id, "score": round(self.score, 4), **self.chunk.meta}
        if with_text:
            out["text"] = self.chunk.text
        return out


class VectorStore:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, manifest: dict[str, Any]) -> None:
        assert len(chunks) == vectors.shape[0]
        self.chunks = chunks
        self.vectors = vectors.astype(np.float32)
        self.manifest = manifest

    @staticmethod
    def corpus_sha256(chunks: list[Chunk]) -> str:
        return hashlib.sha256(json.dumps([c.to_dict() for c in chunks], sort_keys=True).encode()).hexdigest()

    @classmethod
    def build(cls, chunks: list[Chunk], vectors: np.ndarray, embedder_state: dict[str, Any], embedder: str,
              model: str) -> "VectorStore":
        manifest = {"embedder": embedder, "model": model, "dim": int(vectors.shape[1]), "count": len(chunks),
                    "corpus_sha256": cls.corpus_sha256(chunks),
                    "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "embedder_state": embedder_state}
        return cls(chunks, vectors, manifest)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        (directory / "chunks.json").write_text(json.dumps([c.to_dict() for c in self.chunks], indent=1,
                                                          ensure_ascii=False), "utf-8")
        (directory / "manifest.json").write_text(json.dumps(self.manifest, indent=1), "utf-8")

    @classmethod
    def load(cls, directory: Path) -> "VectorStore | None":
        if not (directory / "manifest.json").exists():
            return None
        manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
        chunks = [Chunk(**c) for c in json.loads((directory / "chunks.json").read_text("utf-8"))]
        vectors = np.load(directory / "vectors.npy", allow_pickle=False)
        return cls(chunks, vectors, manifest)

    def search(self, query: np.ndarray, k: int = 4, where: dict[str, Any] | None = None) -> list[Hit]:
        mask = np.ones(len(self.chunks), dtype=bool)
        for key, value in (where or {}).items():
            mask &= np.array([c.meta.get(key) == value for c in self.chunks], dtype=bool)
        if not mask.any():
            return []
        scores = self.vectors @ query.astype(np.float32).reshape(-1)
        scores = np.where(mask, scores, -np.inf)
        order = np.argsort(-scores, kind="stable")[:k]
        return [Hit(self.chunks[i], float(scores[i])) for i in order if np.isfinite(scores[i])]
