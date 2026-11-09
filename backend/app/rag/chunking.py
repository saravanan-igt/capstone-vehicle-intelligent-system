"""Splits policy and vehicle documents into retrievable chunks with filterable metadata."""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def policy_chunks(policy_dir: Path) -> list[Chunk]:
    """One chunk per clause. Clause texts are verbatim from the prose document (checked at extraction time)."""
    chunks: list[Chunk] = []
    for path in sorted(policy_dir.glob("*.json")):
        doc = json.loads(path.read_text("utf-8"))
        source = doc.get("source_document") or path.as_posix()
        for clause in doc["clauses"]:
            text = (f"{doc['lender_name']} policy {doc['policy_code']} version {doc['version']}, "
                    f"clause {clause['section']} {clause['title']}: {clause['text']}")
            chunks.append(Chunk(
                id=f"policy:{doc['policy_code']}:{doc['version']}:{clause['id']}", text=text,
                meta={"doc_type": "policy", "policy_code": doc["policy_code"], "version": doc["version"],
                      "lender_name": doc["lender_name"], "clause_id": clause["id"], "section": clause["section"],
                      "title": clause["title"], "page": clause["page"], "source": source}))
    return chunks


_HEADING = re.compile(r"^## (.+)$", re.MULTILINE)


def vehicle_chunks(vehicle_dir: Path, root: Path) -> list[Chunk]:
    """One chunk per brochure section, prefixed with the model name so each chunk stands alone."""
    chunks: list[Chunk] = []
    for path in sorted(vehicle_dir.glob("*.md")):
        text = path.read_text("utf-8")
        title = text.splitlines()[0].lstrip("# ").replace(" brochure (synthetic)", "").strip()
        make, _, model = title.partition(" ")
        parts = _HEADING.split(text)
        intro, sections = parts[0], list(zip(parts[1::2], parts[2::2]))
        body_type = re.search(r"Body type: (\w+)", intro)
        source = path.relative_to(root).as_posix()
        for heading, body in sections:
            chunks.append(Chunk(
                id=f"vehicle:{path.stem}:{_slug(heading)}", text=f"{title}. {heading}.\n{body.strip()}",
                meta={"doc_type": "vehicle", "model_key": path.stem, "make": make, "model": model,
                      "body_type": body_type.group(1) if body_type else None, "section": heading,
                      "source": source}))
    return chunks


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def corpus(root: Path) -> list[Chunk]:
    docs = root / "data" / "documents"
    return policy_chunks(docs / "policy") + vehicle_chunks(docs / "vehicles", root)
