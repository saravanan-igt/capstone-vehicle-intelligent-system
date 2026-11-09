"""Knowledge base: picks the best available index (Gemini if a key and index exist, else local) and searches it."""

import logging
from pathlib import Path
from typing import Any

from app.rag.embeddings import Embedder, EmbeddingUnavailable, GeminiEmbedder, LocalEmbedder
from app.rag.store import Hit, VectorStore

log = logging.getLogger(__name__)
# Minimum cosine similarity for a chunk to count as relevant (calibrated per embedder; see docs/EVALUATION.md).
MIN_SCORE = {"local": 0.05, "gemini": 0.55}


class KnowledgeBase:
    def __init__(self, primary: tuple[VectorStore, Embedder], fallback: tuple[VectorStore, Embedder] | None = None):
        self.primary = primary
        self.fallback = fallback

    @property
    def name(self) -> str:
        store, embedder = self.primary
        return f"{embedder.name}:{store.manifest['model']}"

    @classmethod
    def load(cls, vectorstore_dir: Path, gemini_api_key: str | None = None) -> "KnowledgeBase | None":
        local_store = VectorStore.load(vectorstore_dir / "local")
        local = None
        if local_store is not None:
            state = local_store.manifest["embedder_state"]
            local = (local_store, LocalEmbedder(dim=state["dim"], idf=state["idf"]))
        gemini_store = VectorStore.load(vectorstore_dir / "gemini") if gemini_api_key else None
        if gemini_store is not None and gemini_api_key:
            try:
                embedder = GeminiEmbedder(gemini_api_key, gemini_store.manifest["model"], gemini_store.manifest["dim"])
                return cls((gemini_store, embedder), local)
            except Exception as exc:
                log.warning("gemini embedder init failed (%s); using local index", type(exc).__name__)
        if local is None:
            log.warning("no vector store in %s; run `python -m app.rag.ingest`", vectorstore_dir)
            return None
        return cls(local)

    def search(self, query: str, k: int = 4, where: dict[str, Any] | None = None) -> tuple[list[Hit], float, str]:
        """Returns (hits, relevance threshold for the index used, index name)."""
        for store, embedder in filter(None, (self.primary, self.fallback)):
            try:
                vector = embedder.embed([query], "query")[0]
            except EmbeddingUnavailable:
                continue
            return store.search(vector, k, where), MIN_SCORE[embedder.name], f"{embedder.name}:{store.manifest['model']}"
        return [], 1.0, "unavailable"
