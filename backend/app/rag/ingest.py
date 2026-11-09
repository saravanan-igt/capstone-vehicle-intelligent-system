"""Builds the vector indexes from data/documents.

    python -m app.rag.ingest            # local index; plus Gemini index when GEMINI_API_KEY is set
    python -m app.rag.ingest --local-only
"""

import argparse
import os

from app.config import assets_dir
from app.rag.chunking import corpus
from app.rag.embeddings import GeminiEmbedder, LocalEmbedder
from app.rag.store import VectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--local-only", action="store_true", help="skip the Gemini embedding index")
    args = parser.parse_args()
    root = assets_dir()
    chunks = corpus(root)
    texts = [c.text for c in chunks]
    out = root / "vectorstore"

    local = LocalEmbedder().fit(texts)
    VectorStore.build(chunks, local.embed(texts, "document"), local.state(), local.name, local.model).save(out / "local")
    print(f"local index: {len(chunks)} chunks -> {out / 'local'}")

    key = os.getenv("GEMINI_API_KEY")
    if key and not args.local_only:
        gemini = GeminiEmbedder(key)
        VectorStore.build(chunks, gemini.embed(texts, "document"), gemini.state(), gemini.name,
                          gemini.model).save(out / "gemini")
        print(f"gemini index: {len(chunks)} chunks ({gemini.model}, {gemini.dim} dims) -> {out / 'gemini'}")
    elif not args.local_only:
        print("GEMINI_API_KEY not set: skipped the Gemini index (the local index is used at runtime)")


if __name__ == "__main__":
    main()
