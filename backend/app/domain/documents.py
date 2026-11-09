"""Pure policy-document rules: file-type sniffing, page/chunk handling, clause grounding and keyword retrieval.
Document text is data only; nothing here interprets it as instructions or code."""

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

MAX_PAGES = 60
MAX_PAGE_CHARS = 30_000
CHUNK_CHARS = 1_200

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


class PageText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1)
    text: str


class Transcription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pages: list[PageText]


def sniff_mime(data: bytes) -> str | None:
    """Content-based type detection; the client-declared type is never trusted on its own."""
    return next((mime for sig, mime in _SIGNATURES if data.startswith(sig)), None)


def safe_filename(raw: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._ \-]", "_", raw.replace("\\", "/").rsplit("/", 1)[-1]).strip(" .")
    return name[:120] or "document"


def validate_pages(pages: list[PageText]) -> list[str]:
    problems: list[str] = []
    if not pages:
        return ["no pages were transcribed"]
    if len(pages) > MAX_PAGES:
        problems.append(f"document has {len(pages)} pages; the limit is {MAX_PAGES}")
    numbers = [p.page for p in pages]
    if numbers != list(range(1, len(pages) + 1)):
        problems.append("page numbers must be 1..N in order without gaps or duplicates")
    for p in pages:
        if len(p.text) > MAX_PAGE_CHARS:
            problems.append(f"page {p.page} exceeds {MAX_PAGE_CHARS} characters")
    if not any(p.text.strip() for p in pages):
        problems.append("no text was found in the document")
    return problems


_SECTION = re.compile(r"^\s*(?:section\s+|clause\s+|§\s*)?(\d+(?:\.\d+){0,4})\b", re.IGNORECASE | re.MULTILINE)


def chunk_page(page: PageText, max_chars: int = CHUNK_CHARS) -> list[dict[str, Any]]:
    """Split a page into paragraph-aligned chunks; joining the chunks reproduces the paragraphs in order."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
    pieces: list[str] = []
    for para in paragraphs:
        while len(para) > max_chars:
            cut = para.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            pieces.append(para[:cut].strip())
            para = para[cut:].strip()
        if para:
            pieces.append(para)
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + 2 + len(piece) <= max_chars:
            chunks[-1] = f"{chunks[-1]}\n\n{piece}"
        else:
            chunks.append(piece)
    out = []
    for seq, text in enumerate(chunks, start=1):
        match = _SECTION.search(text)
        out.append({"page": page.page, "seq": seq, "section": match.group(1) if match else None, "text": text})
    return out


_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                         "\u2212": "-", "\u00a0": " ", "\u20b9": "rs."})


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).lower()
    text = re.sub(r"\brs\.?\s*", "rs. ", text)
    return re.sub(r"\s+", " ", text).strip()


def ground_clauses(clauses: list[Any], pages: dict[int, str]) -> list[dict[str, str]]:
    """Every clause must quote text that appears on its cited page of the stored source document."""
    problems: list[dict[str, str]] = []
    normalised = {n: normalise_text(t) for n, t in pages.items()}
    for i, clause in enumerate(clauses):
        if not isinstance(clause, dict):
            problems.append({"loc": f"clauses.{i}", "msg": "clause must be an object"})
            continue
        cid, page, text = clause.get("id", f"#{i}"), clause.get("page"), clause.get("text")
        if not isinstance(page, int) or page not in normalised:
            problems.append({"loc": f"clauses.{i}.page", "msg": f"clause {cid}: page {page} is not in the source"})
            continue
        if not isinstance(text, str) or not text.strip():
            problems.append({"loc": f"clauses.{i}.text", "msg": f"clause {cid}: text is empty"})
            continue
        if normalise_text(text) not in normalised[page]:
            problems.append({"loc": f"clauses.{i}.text",
                             "msg": f"clause {cid}: text is not found verbatim on page {page} of the source"})
    return problems


_TERM = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")


def search_chunks(chunks: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Deterministic keyword retrieval for reviewers. Not used to choose which eligibility rules run."""
    terms = {t for t in _TERM.findall(normalise_text(query)) if len(t) > 1}
    if not terms:
        return []
    scored = []
    for chunk in chunks:
        words = _TERM.findall(normalise_text(chunk["text"]))
        hits = {t: words.count(t) for t in terms}
        matched = sum(1 for n in hits.values() if n)
        if matched:
            scored.append((matched, sum(hits.values()), chunk))
    scored.sort(key=lambda s: (-s[0], -s[1], s[2]["page"], s[2]["seq"]))
    return [{**c, "score": m * 100 + n} for m, n, c in scored[:limit]]
