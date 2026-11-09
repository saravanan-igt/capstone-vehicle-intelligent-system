"""Vehicle Q&A grounded in brochure chunks. Says "I don't know" rather than guessing."""

import re
from typing import Any, Protocol

from app.rag.embeddings import terms
from app.rag.knowledge import KnowledgeBase
from app.rag.store import Hit

# Words that say what kind of thing is asked about, not which fact; they cannot make a chunk relevant on their own.
GENERIC = frozenset("available option variant model car vehicle offer come support feature include standard "
                    "there have get much many does good best really".split())
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class AnswerUnavailable(RuntimeError):
    pass


class VehicleAnswerer(Protocol):
    name: str
    model: str | None

    def answer(self, question: str, vehicle: str, sources: list[dict[str, Any]]) -> dict[str, Any]: ...


def dont_know(vehicle_name: str) -> str:
    return (f"I don't know. The brochure and specifications we have for the {vehicle_name} do not cover that. "
            "Please check with the dealer.")


def _key_terms(question: str, vehicle_name: str) -> set[str]:
    names = set(terms(vehicle_name))
    return {t for t in terms(question) if t not in GENERIC and t not in names}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def grounded(answer: str, sources: list[dict[str, Any]], question: str) -> bool:
    """Every number in the answer must appear in a source (or the question)."""
    allowed = _numbers(question)
    for s in sources:
        allowed |= _numbers(s["text"])
    return _numbers(answer) <= allowed


def extractive_answer(question: str, vehicle_name: str, hits: list[Hit]) -> str | None:
    """Returns the brochure lines that best match the question's key terms (no generation)."""
    wanted = _key_terms(question, vehicle_name)
    scored: list[tuple[int, int, str]] = []
    for rank, hit in enumerate(hits):
        lines = [line.strip("- ").strip() for line in hit.chunk.text.splitlines()[1:] if line.strip()]
        for line in lines:
            overlap = len(wanted & set(terms(line)))
            if overlap:
                scored.append((-overlap, rank, line))
    if not scored:
        return None
    scored.sort()
    best = -scored[0][0]
    picked = [line for neg, _, line in scored if -neg == best][:3]
    return " ".join(line if line.endswith(".") else f"{line}." for line in picked)


def answer_question(kb: KnowledgeBase | None, vehicle: dict[str, Any], question: str,
                    answerer: VehicleAnswerer | None) -> dict[str, Any]:
    vehicle_name = f"{vehicle['make']} {vehicle['model']}"
    model_key = vehicle["model_key"]
    base = {"vehicle_id": vehicle["id"], "question": question}
    if kb is None:
        return {**base, "answerable": False, "answer": dont_know(vehicle_name), "mode": "unavailable",
                "index": None, "sources": []}
    hits, threshold, index = kb.search(question, 4, {"doc_type": "vehicle", "model_key": model_key})
    wanted = _key_terms(question, vehicle_name)
    relevant = [h for h in hits if h.score >= threshold and wanted & set(terms(h.chunk.text))]
    sources = [h.to_dict() for h in relevant]
    if not relevant:
        return {**base, "answerable": False, "answer": dont_know(vehicle_name), "mode": "retrieval",
                "index": index, "sources": []}
    if answerer is not None:
        try:
            drafted = answerer.answer(question, vehicle_name, sources)
            cited = [s for s in sources if s["id"] in set(drafted.get("source_ids") or [])]
            if not drafted.get("answerable"):
                return {**base, "answerable": False, "answer": dont_know(vehicle_name), "mode": "ai",
                        "index": index, "sources": []}
            if cited and grounded(drafted["answer"], cited, question):
                return {**base, "answerable": True, "answer": drafted["answer"], "mode": "ai", "index": index,
                        "sources": cited}
        except AnswerUnavailable:
            pass
    text = extractive_answer(question, vehicle_name, relevant)
    if text is None:
        return {**base, "answerable": False, "answer": dont_know(vehicle_name), "mode": "extractive",
                "index": index, "sources": []}
    return {**base, "answerable": True, "answer": f"From the {vehicle_name} brochure: {text}", "mode": "extractive",
            "index": index, "sources": sources}
