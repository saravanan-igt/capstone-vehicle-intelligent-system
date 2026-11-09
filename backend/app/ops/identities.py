"""Link IdP subjects (issuer + sub) to local users. Authorization still comes from tenant memberships.

    python -m app.ops.identities link --issuer https://cognito-idp.<region>.amazonaws.com/<pool> --subject <sub> --user u-alice
    python -m app.ops.identities list
    python -m app.ops.identities link-demo --issuer http://localhost:8080/vla   # DEMO ONLY: subject == seed user id

Uses DATABASE_ADMIN_URL, falling back to DATABASE_URL."""

import argparse
import json
import os
import sys

from sqlalchemy import select

from app.infrastructure.db import make_engine, make_session_factory, session_scope
from app.infrastructure.models import User, UserIdentity
from app.seed.seed import USERS


def _factory():  # type: ignore[no-untyped-def]
    url = os.getenv("DATABASE_ADMIN_URL") or os.getenv("DATABASE_URL", "sqlite:///./data/vla.db")
    return make_session_factory(make_engine(url))


def link(issuer: str, subject: str, user_id: str) -> dict[str, str]:
    issuer = issuer.rstrip("/")
    with session_scope(_factory()) as s:
        if s.get(User, user_id) is None:
            raise SystemExit(f"unknown user: {user_id}")
        existing = s.scalar(select(UserIdentity).where(UserIdentity.issuer == issuer, UserIdentity.subject == subject))
        if existing is not None and existing.user_id != user_id:
            raise SystemExit(f"subject already linked to {existing.user_id}")
        if existing is None:
            s.add(UserIdentity(issuer=issuer, subject=subject, user_id=user_id))
    return {"issuer": issuer, "subject": subject, "user_id": user_id}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.ops.identities")
    sub = parser.add_subparsers(dest="cmd", required=True)
    lk = sub.add_parser("link")
    lk.add_argument("--issuer", required=True)
    lk.add_argument("--subject", required=True)
    lk.add_argument("--user", required=True)
    demo = sub.add_parser("link-demo")
    demo.add_argument("--issuer", required=True)
    sub.add_parser("list")
    args = parser.parse_args(argv)
    if args.cmd == "link":
        print(json.dumps(link(args.issuer, args.subject, args.user)))
    elif args.cmd == "link-demo":
        print(json.dumps([link(args.issuer, user_id, user_id) for user_id, *_ in USERS]))
    else:
        with session_scope(_factory()) as s:
            rows = s.scalars(select(UserIdentity).order_by(UserIdentity.user_id))
            print(json.dumps([{"issuer": r.issuer, "subject": r.subject, "user_id": r.user_id} for r in rows]))


if __name__ == "__main__":
    main(sys.argv[1:])
