"""Idempotent loader for SYNTHETIC tenants, users, published policies, and the vehicle catalogue."""

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services import canonical_json, sha256
from app.config import assets_dir
from app.domain.policy import PolicyDocument
from app.infrastructure.models import Membership, PolicyVersion, Tenant, User, Vehicle, VehiclePrice

POLICY_DIR = assets_dir() / "data" / "documents" / "policy"
CATALOGUE = assets_dir() / "data" / "raw" / "vehicles.json"
log = logging.getLogger(__name__)

TENANTS = [
    ("t-northwind", "Northwind Auto Finance (synthetic)", "NW-AUTO-STD-2026.1.json"),
    ("t-southbay", "Southbay Motor Credit (synthetic)", "SB-AUTO-PRIME-2026.1.json"),
]

USERS = [
    ("u-alice", "alice@example.test", "Alice Applicant", [("t-northwind", "applicant")]),
    ("u-arjun", "arjun@example.test", "Arjun Applicant", [("t-northwind", "applicant")]),
    ("u-omar", "omar@example.test", "Omar Officer", [("t-northwind", "loan_officer")]),
    ("u-priya", "priya@example.test", "Priya Policy Admin", [("t-northwind", "policy_admin")]),
    ("u-tara", "tara@example.test", "Tara Tenant Admin", [("t-northwind", "tenant_admin")]),
    ("u-ben", "ben@example.test", "Ben Applicant", [("t-southbay", "applicant")]),
    ("u-lena", "lena@example.test", "Lena Officer", [("t-southbay", "loan_officer"), ("t-southbay", "policy_admin")]),
]


def seed(session: Session) -> None:
    for tenant_id, name, policy_file in TENANTS:
        if session.get(Tenant, tenant_id) is None:
            session.add(Tenant(id=tenant_id, name=name, kind="lender", default_product="new-car-fixed",
                               currency="INR", jurisdiction="IN"))
            session.flush()
        doc = PolicyDocument.model_validate_json((POLICY_DIR / policy_file).read_text("utf-8"))
        body = canonical_json(doc.model_dump(mode="json"))
        existing = session.scalar(select(PolicyVersion).where(
            PolicyVersion.tenant_id == tenant_id, PolicyVersion.policy_code == doc.policy_code,
            PolicyVersion.version == doc.version))
        if existing is not None and existing.content_sha256 != sha256(body):
            # Published versions are immutable; an old local demo database must be reset, not edited.
            log.warning("seeded policy %s %s differs from %s; reset the local demo database "
                        "(python run.py --reset-db, or docker compose down -v)", doc.policy_code, doc.version,
                        policy_file)
        if existing is None:
            session.add(PolicyVersion(
                tenant_id=tenant_id, policy_code=doc.policy_code, version=doc.version, product=doc.product,
                status="PUBLISHED", document_json=body, content_sha256=sha256(body),
                effective_from=doc.effective_from, effective_to=doc.effective_to, created_by="seed",
                published_by="seed", published_at=datetime.now(timezone.utc)))

    for user_id, email, display, memberships in USERS:
        if session.get(User, user_id) is None:
            session.add(User(id=user_id, email=email, display_name=display))
            session.flush()
            for tenant_id, role in memberships:
                session.add(Membership(user_id=user_id, tenant_id=tenant_id, role=role))

    catalogue = json.loads(CATALOGUE.read_text("utf-8"))
    for v in catalogue["vehicles"]:
        if session.get(Vehicle, v["id"]) is not None:
            continue
        session.add(Vehicle(id=v["id"], make=v["make"], model=v["model"], variant=v["variant"],
                            body_type=v["body_type"], fuel_type=v["fuel_type"], category=v["category"],
                            transmission=v["transmission"], seating=v["seating"], specs_json=json.dumps(v["specs"]),
                            source=catalogue["source"], source_ref=v.get("brochure") or f"vehicles.json#{v['id']}"))
        session.flush()
        for pr in v["prices"]:
            session.add(VehiclePrice(vehicle_id=v["id"], region=pr["region"], currency="INR",
                                     ex_showroom=pr["ex_showroom"], registration=pr["registration"],
                                     insurance=pr["insurance"], other_charges=pr["other_charges"],
                                     price_date=date.fromisoformat(pr["price_date"]), source=catalogue["source"]))
    session.flush()
