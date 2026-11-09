"""Policy-document ingestion use cases: upload -> transcription -> chunks -> AI draft -> human review -> policy draft.
Nothing here can publish a policy; publication stays an explicit, separately authorised step."""

import hashlib
import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errors import AppError, conflict, not_found, unprocessable
from app.application.security import Principal
from app.application.services import _iso, audit, canonical_json, create_policy_draft, sha256
from app.domain import documents
from app.domain.documents import PageText
from app.domain.policy import PolicyDocument
from app.infrastructure.document_ai import DocumentAI, DocumentAIUnavailable
from app.infrastructure.models import (
    OutboxEvent,
    PolicyChunk,
    PolicyDocumentPage,
    PolicySourceDocument,
    PolicyVersion,
    Tenant,
    utcnow,
)
from app.infrastructure.quota import Quota, UnlimitedQuota
from app.infrastructure.storage import DocumentStore

TOPIC_TRANSCRIBE = "document.transcribe"
TOPIC_EXTRACT = "document.extract"
BUDGET_EXHAUSTED = "Tenant AI budget exhausted for today"


def _has_text(row: PolicySourceDocument) -> bool:
    return row.text_version > 0


def _require_ai_budget(quota: Quota, tenant_id: str) -> None:
    if not quota.allow_ai(tenant_id):
        raise DocumentAIUnavailable(BUDGET_EXHAUSTED)


def document_view(row: PolicySourceDocument) -> dict[str, Any]:
    return {"id": row.id, "filename": row.filename, "mime_type": row.mime_type, "size_bytes": row.size_bytes,
            "sha256": row.sha256, "status": row.status, "text_version": row.text_version,
            "page_count": row.page_count, "ocr_model": row.ocr_model, "error": row.error,
            "extraction_model": row.extraction_model, "policy_version_id": row.policy_version_id,
            "uploaded_by": row.uploaded_by, "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at)}


def _doc(session: Session, p: Principal, doc_id: str) -> PolicySourceDocument:
    row = session.scalar(select(PolicySourceDocument).where(PolicySourceDocument.tenant_id == p.tenant_id,
                                                            PolicySourceDocument.id == doc_id))
    if row is None:
        raise not_found("Policy document")
    return row


def _pages(session: Session, row: PolicySourceDocument) -> list[PageText]:
    rows = session.scalars(select(PolicyDocumentPage).where(
        PolicyDocumentPage.tenant_id == row.tenant_id, PolicyDocumentPage.document_id == row.id,
        PolicyDocumentPage.text_version == row.text_version).order_by(PolicyDocumentPage.page))
    return [PageText(page=r.page, text=r.text) for r in rows]


def _source_ref(row: PolicySourceDocument) -> str:
    return f"{row.filename} (document {row.id}, sha256 {row.sha256[:16]})"


def upload_document(session: Session, p: Principal, store: DocumentStore, data: bytes, declared_type: str,
                    filename: str, cid: str | None) -> tuple[PolicySourceDocument, bool]:
    p.require("policy:write")
    if not data:
        raise unprocessable("EMPTY_UPLOAD", "The uploaded file is empty")
    mime = documents.sniff_mime(data)
    declared = declared_type.split(";", 1)[0].strip().lower()
    if mime is None or mime != declared:
        raise AppError(415, "UNSUPPORTED_MEDIA_TYPE",
                       "Upload a PDF, PNG or JPEG; the declared type must match the file content")
    digest = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(PolicySourceDocument).where(PolicySourceDocument.tenant_id == p.tenant_id,
                                                                 PolicySourceDocument.sha256 == digest))
    if existing is not None:
        return existing, False
    key = store.put(p.tenant_id, digest, data)
    row = PolicySourceDocument(tenant_id=p.tenant_id, filename=documents.safe_filename(filename), mime_type=mime,
                               size_bytes=len(data), sha256=digest, storage_key=key, status="UPLOADED",
                               uploaded_by=p.user_id)
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict("DOCUMENT_UPLOAD_IN_PROGRESS", "The same document is being uploaded concurrently") from exc
    audit(session, p, "policy_document.uploaded", "policy_document", row.id,
          {"sha256": digest, "size_bytes": len(data), "mime_type": mime}, cid)
    return row, True


def transcribe_document(session: Session, p: Principal, store: DocumentStore, ai: DocumentAI, doc_id: str,
                        cid: str | None, quota: Quota | None = None,
                        retryable: bool = False) -> PolicySourceDocument:
    """With retryable=True (worker, non-final attempt) AI failures propagate so the job is retried with backoff."""
    p.require("policy:write")
    row = _doc(session, p, doc_id)
    data = store.get(row.storage_key)
    if hashlib.sha256(data).hexdigest() != row.sha256:
        raise AppError(500, "DOCUMENT_INTEGRITY_FAILED", "Stored document does not match its recorded hash")
    try:
        _require_ai_budget(quota or UnlimitedQuota(), row.tenant_id)
        pages = ai.transcribe(data, row.mime_type)
        problems = documents.validate_pages(pages)
        if problems:
            raise DocumentAIUnavailable("Transcription rejected: " + "; ".join(problems))
    except DocumentAIUnavailable as exc:
        if retryable:
            raise
        row.status, row.error, row.updated_at = "TEXT_FAILED", str(exc), utcnow()
        row.pending_job_id = None
        audit(session, p, "policy_document.transcription_failed", "policy_document", row.id, {"error": str(exc)}, cid)
        return row
    version = row.text_version + 1
    for page in pages:
        session.add(PolicyDocumentPage(tenant_id=row.tenant_id, document_id=row.id, text_version=version,
                                       page=page.page, text=page.text))
        for chunk in documents.chunk_page(page):
            session.add(PolicyChunk(tenant_id=row.tenant_id, document_id=row.id, text_version=version,
                                    page=chunk["page"], seq=chunk["seq"], section=chunk["section"],
                                    text=chunk["text"], sha256=sha256(chunk["text"])))
    row.text_version, row.page_count, row.ocr_model = version, len(pages), ai.model
    row.status, row.error, row.updated_at = "TEXT_EXTRACTED", None, utcnow()
    row.extraction_json = row.extraction_problems_json = row.extraction_model = None
    row.pending_job_id = None
    session.flush()
    audit(session, p, "policy_document.transcribed", "policy_document", row.id,
          {"text_version": version, "pages": len(pages), "model": ai.model}, cid)
    return row


def review_problems(candidate: dict[str, Any], pages: list[PageText]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    try:
        PolicyDocument.model_validate(candidate)
    except ValidationError as exc:
        problems += [{"loc": ".".join(str(x) for x in e["loc"]), "msg": e["msg"]}
                     for e in exc.errors(include_url=False, include_context=False)]
    clauses = candidate.get("clauses")
    if isinstance(clauses, list):
        problems += documents.ground_clauses(clauses, {pg.page: pg.text for pg in pages})
    return problems


def extract_draft(session: Session, p: Principal, ai: DocumentAI, doc_id: str, cid: str | None,
                  quota: Quota | None = None, retryable: bool = False) -> dict[str, Any]:
    p.require("policy:write")
    row = _doc(session, p, doc_id)
    if not _has_text(row):
        raise conflict("DOCUMENT_HAS_NO_TEXT", "Transcribe the document before extracting draft rules")
    pages = _pages(session, row)
    try:
        _require_ai_budget(quota or UnlimitedQuota(), row.tenant_id)
        candidate = ai.extract_policy(pages)
    except DocumentAIUnavailable as exc:
        if retryable:
            raise
        row.status, row.error, row.updated_at = "EXTRACTION_FAILED", str(exc), utcnow()
        row.pending_job_id = None
        audit(session, p, "policy_document.extraction_failed", "policy_document", row.id, {"error": str(exc)}, cid)
        return document_detail(session, p, row.id)
    tenant = session.get(Tenant, p.tenant_id)
    # Server-owned fields: provenance is never taken from model output.
    candidate["source_document"] = _source_ref(row)
    candidate["schema_version"] = "1"
    if not candidate.get("product") and tenant is not None:
        candidate["product"] = tenant.default_product
    problems = review_problems(candidate, pages)
    row.extraction_json, row.extraction_problems_json = canonical_json(candidate), canonical_json(problems)
    row.extraction_model, row.status, row.error, row.updated_at = ai.model, "DRAFT_EXTRACTED", None, utcnow()
    row.pending_job_id = None
    audit(session, p, "policy_document.draft_extracted", "policy_document", row.id,
          {"model": ai.model, "problems": len(problems)}, cid)
    return document_detail(session, p, row.id)


def create_draft_from_document(session: Session, p: Principal, doc_id: str, payload: dict[str, Any],
                               cid: str | None) -> PolicyVersion:
    p.require("policy:write")
    row = _doc(session, p, doc_id)
    if not _has_text(row):
        raise conflict("DOCUMENT_HAS_NO_TEXT", "Transcribe the document before creating a policy draft")
    payload = {**payload, "source_document": _source_ref(row)}
    try:
        doc = PolicyDocument.model_validate(payload)
    except ValidationError as exc:
        raise unprocessable("INVALID_POLICY", "Policy document failed validation",
                            exc.errors(include_url=False, include_context=False)) from exc
    grounding = documents.ground_clauses([c.model_dump() for c in doc.clauses],
                                         {pg.page: pg.text for pg in _pages(session, row)})
    if grounding:
        raise unprocessable("CLAUSES_NOT_GROUNDED", "Clause text must appear verbatim on the cited source page",
                            grounding)
    version = create_policy_draft(session, p, doc, cid)
    edited = row.extraction_json is None or canonical_json(payload) != canonical_json(
        {**json.loads(row.extraction_json), "source_document": payload["source_document"]})
    row.policy_version_id, row.status, row.updated_at = version.id, "DRAFT_CREATED", utcnow()
    audit(session, p, "policy_document.reviewed", "policy_document", row.id,
          {"policy_version_id": version.id, "reviewer": p.user_id, "edited_by_reviewer": edited,
           "extraction_model": row.extraction_model, "text_version": row.text_version}, cid)
    return version


def list_documents(session: Session, p: Principal) -> list[dict[str, Any]]:
    p.require("policy_document:read")
    rows = session.scalars(select(PolicySourceDocument).where(PolicySourceDocument.tenant_id == p.tenant_id)
                           .order_by(PolicySourceDocument.created_at.desc()))
    return [document_view(r) for r in rows]


def document_detail(session: Session, p: Principal, doc_id: str) -> dict[str, Any]:
    p.require("policy_document:read")
    row = _doc(session, p, doc_id)
    view = document_view(row)
    view["pages"] = [pg.model_dump() for pg in _pages(session, row)]
    view["extraction"] = json.loads(row.extraction_json) if row.extraction_json else None
    view["extraction_problems"] = json.loads(row.extraction_problems_json) if row.extraction_problems_json else []
    return view


def document_file(session: Session, p: Principal, store: DocumentStore, doc_id: str) -> tuple[bytes, str, str]:
    p.require("policy_document:read")
    row = _doc(session, p, doc_id)
    return store.get(row.storage_key), row.mime_type, row.filename


def search_document(session: Session, p: Principal, doc_id: str, query: str, limit: int) -> dict[str, Any]:
    p.require("policy_document:read")
    row = _doc(session, p, doc_id)
    rows = session.scalars(select(PolicyChunk).where(
        PolicyChunk.tenant_id == p.tenant_id, PolicyChunk.document_id == row.id,
        PolicyChunk.text_version == row.text_version))
    chunks = [{"page": c.page, "seq": c.seq, "section": c.section, "text": c.text} for c in rows]
    return {"document_id": row.id, "text_version": row.text_version, "query": query,
            "items": documents.search_chunks(chunks, query, max(1, min(limit, 25)))}


def source_document_for_policy(session: Session, tenant_id: str, version_id: str) -> str | None:
    return session.scalar(select(PolicySourceDocument.id).where(
        PolicySourceDocument.tenant_id == tenant_id, PolicySourceDocument.policy_version_id == version_id))


# ---------- background processing (DOCUMENT_PROCESSING=queue) ----------

def request_processing(session: Session, p: Principal, doc_id: str, topic: str,
                       cid: str | None) -> PolicySourceDocument:
    """Records the job in the outbox in the same transaction as the state change (no lost or phantom jobs)."""
    p.require("policy:write")
    row = _doc(session, p, doc_id)
    if row.pending_job_id is not None:
        raise conflict("DOCUMENT_BUSY", "This document already has processing in progress")
    if topic == TOPIC_EXTRACT and not _has_text(row):
        raise conflict("DOCUMENT_HAS_NO_TEXT", "Transcribe the document before extracting draft rules")
    # Only references travel through the queue; document content stays in the database and object store.
    event = OutboxEvent(tenant_id=row.tenant_id, topic=topic, payload_json=canonical_json(
        {"v": 1, "document_id": row.id, "tenant_id": row.tenant_id, "requested_by": p.user_id,
         "correlation_id": cid}))
    session.add(event)
    session.flush()
    row.pending_job_id, row.status, row.error, row.updated_at = event.id, "PROCESSING", None, utcnow()
    audit(session, p, "policy_document.queued", "policy_document", row.id, {"topic": topic, "job_id": event.id}, cid)
    return row


def worker_principal(tenant_id: str) -> Principal:
    return Principal(user_id="system:document-worker", email="", display_name="Document worker", tenant_id=tenant_id,
                     roles=frozenset({"policy_admin"}), available_tenants=(tenant_id,))


def run_document_job(session: Session, store: DocumentStore, ai: DocumentAI, quota: Quota, job_id: str, topic: str,
                     payload: dict[str, Any], final_attempt: bool) -> str:
    """Idempotent handler. Returns 'skipped' for duplicate or stale deliveries. Raises DocumentAIUnavailable on a
    retryable failure; on the final attempt the failure is recorded on the document instead."""
    p = worker_principal(payload["tenant_id"])
    row = session.scalar(select(PolicySourceDocument).where(PolicySourceDocument.tenant_id == p.tenant_id,
                                                            PolicySourceDocument.id == payload["document_id"]))
    if row is None or row.pending_job_id != job_id:
        return "skipped"
    cid = payload.get("correlation_id")
    if topic == TOPIC_TRANSCRIBE:
        transcribe_document(session, p, store, ai, row.id, cid, quota, retryable=not final_attempt)
    elif topic == TOPIC_EXTRACT:
        extract_draft(session, p, ai, row.id, cid, quota, retryable=not final_attempt)
    else:
        raise ValueError(f"unknown topic {topic}")
    return "completed"
