"""Privileged one-shot: apply migrations and load seed data. Run with the owner role, never by the API at runtime.

    DATABASE_ADMIN_URL=postgresql://vla_owner:...@db/vla python -m app.ops.migrate [--no-seed]"""

import argparse
import json
import os
import sys

from app.infrastructure.db import make_engine, make_session_factory, migrate, session_scope
from app.seed.seed import seed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.ops.migrate")
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args(argv)
    url = os.getenv("DATABASE_ADMIN_URL") or os.getenv("DATABASE_URL", "sqlite:///./data/vla.db")
    engine = make_engine(url)
    migrate(engine)
    if not args.no_seed:
        with session_scope(make_session_factory(engine)) as s:
            seed(s)
    engine.dispose()
    print(json.dumps({"migrated": True, "seeded": not args.no_seed, "dialect": engine.dialect.name}))


if __name__ == "__main__":
    main(sys.argv[1:])
