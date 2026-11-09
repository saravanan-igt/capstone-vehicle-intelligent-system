"""SQLAlchemy persistence models. Money is stored as decimal strings (SQLite has no exact NUMERIC);
the PostgreSQL migration path maps these to NUMERIC(14,2) - see docs/ARCHITECTURE.md."""

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="lender")
    default_product: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    jurisdiction: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", "role"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))


class UserIdentity(Base):
    """Links an external IdP subject (issuer + sub) to a local user; authorization still comes from memberships."""

    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEvent(Base):
    """Transactional outbox: written in the same transaction as the business change, relayed to BullMQ."""

    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    topic: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "policy_code", "version"),
        UniqueConstraint("tenant_id", "id"),
        Index("ix_policy_versions_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    policy_code: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(20))
    product: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))  # DRAFT | PUBLISHED | RETIRED
    document_json: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_applications_tenant_created", "tenant_id", "created_at", "id"),
        Index("ix_applications_tenant_applicant", "tenant_id", "applicant_user_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    applicant_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    # Workflow: DRAFT | INCOMPLETE | PROCESSING | NEEDS_REVIEW | COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    input_json: Mapped[str] = mapped_column(Text)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "application_id"], ["applications.tenant_id", "applications.id"]),
        ForeignKeyConstraint(["tenant_id", "policy_version_id"], ["policy_versions.tenant_id", "policy_versions.id"]),
        UniqueConstraint("tenant_id", "idempotency_key"),
        UniqueConstraint("tenant_id", "id"),
        Index("ix_decisions_tenant_application", "tenant_id", "application_id", "evaluated_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64))
    application_id: Mapped[str] = mapped_column(String(32))
    policy_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    eligible_principal: Mapped[str | None] = mapped_column(String(24), nullable=True)
    snapshot_json: Mapped[str] = mapped_column(Text)
    result_sha256: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evaluated_by: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Explanation(Base):
    __tablename__ = "explanations"
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "decision_id"], ["decisions.tenant_id", "decisions.id"]),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64))
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(16))  # gemini | template
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_json: Mapped[str] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Vehicle(Base):
    """Shared catalogue (not tenant-owned). Tenant-specific offers are a later extension."""

    __tablename__ = "vehicles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    make: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    variant: Mapped[str] = mapped_column(String(80))
    body_type: Mapped[str] = mapped_column(String(20), index=True)
    fuel_type: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(20))
    transmission: Mapped[str] = mapped_column(String(20))
    seating: Mapped[int] = mapped_column(Integer)
    specs_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    source_ref: Mapped[str] = mapped_column(String(200))


class VehiclePrice(Base):
    __tablename__ = "vehicle_prices"
    __table_args__ = (UniqueConstraint("vehicle_id", "region", "price_date"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    region: Mapped[str] = mapped_column(String(8))
    currency: Mapped[str] = mapped_column(String(3))
    ex_showroom: Mapped[str] = mapped_column(String(24))
    registration: Mapped[str | None] = mapped_column(String(24), nullable=True)
    insurance: Mapped[str | None] = mapped_column(String(24), nullable=True)
    other_charges: Mapped[str | None] = mapped_column(String(24), nullable=True)
    price_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(200))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_tenant_created", "tenant_id", "created_at", "id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    actor_user_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PolicySourceDocument(Base):
    __tablename__ = "policy_source_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sha256"),
        UniqueConstraint("tenant_id", "id"),
        Index("ix_policy_source_documents_tenant_created", "tenant_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    filename: Mapped[str] = mapped_column(String(120))
    mime_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(160))
    # UPLOADED | PROCESSING | TEXT_FAILED | TEXT_EXTRACTED | EXTRACTION_FAILED | DRAFT_EXTRACTED | DRAFT_CREATED
    status: Mapped[str] = mapped_column(String(24))
    text_version: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_problems_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Outbox/job id the document is waiting for; a delivery with any other id is a duplicate and is skipped.
    pending_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PolicyDocumentPage(Base):
    __tablename__ = "policy_document_pages"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "document_id"],
                             ["policy_source_documents.tenant_id", "policy_source_documents.id"]),
        UniqueConstraint("document_id", "text_version", "page"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64))
    document_id: Mapped[str] = mapped_column(String(32))
    text_version: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "document_id"],
                             ["policy_source_documents.tenant_id", "policy_source_documents.id"]),
        UniqueConstraint("document_id", "text_version", "page", "seq"),
        Index("ix_policy_chunks_tenant_document", "tenant_id", "document_id", "text_version"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64))
    document_id: Mapped[str] = mapped_column(String(32))
    text_version: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(32), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
