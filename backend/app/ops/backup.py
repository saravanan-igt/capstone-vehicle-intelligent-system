"""Consistent local backup/restore for the SQLite database and uploaded policy documents.

    python -m app.ops.backup backup  --db data/vla.db --docs data/documents --out backups
    python -m app.ops.backup verify  --from backups/<stamp>
    python -m app.ops.backup restore --from backups/<stamp> --db data/vla.db --docs data/documents [--force]

Stop the API before restoring. Production uses RDS snapshots/PITR and S3 versioning instead (docs/RUNBOOK.md)."""

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = "manifest.json"
COUNTED_TABLES = ("tenants", "applications", "decisions", "policy_versions", "policy_source_documents",
                  "audit_events")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _table_counts(db: Path) -> dict[str, int]:
    with closing(sqlite3.connect(db)) as conn:
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608 - fixed allow-list
                for t in COUNTED_TABLES if t in existing}


def _integrity(db: Path) -> str:
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]


def backup(db: Path, docs: Path, out: Path) -> Path:
    if not db.is_file():
        raise SystemExit(f"database not found: {db}")
    target = out / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True, exist_ok=False)
    # The online backup API gives a consistent snapshot even while the API is writing (WAL mode).
    with closing(sqlite3.connect(db)) as src, closing(sqlite3.connect(target / "vla.db")) as dst:
        src.backup(dst)
    if docs.is_dir():
        shutil.copytree(docs, target / "documents")
    files = {str(p.relative_to(target)).replace("\\", "/"): _sha256(p)
             for p in sorted(target.rglob("*")) if p.is_file()}
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "source_db": str(db),
                "integrity_check": _integrity(target / "vla.db"), "table_counts": _table_counts(target / "vla.db"),
                "files": files}
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), "utf-8")
    return target


def verify(source: Path) -> dict:
    manifest = json.loads((source / MANIFEST).read_text("utf-8"))
    problems = [name for name, digest in manifest["files"].items()
                if not (source / name).is_file() or _sha256(source / name) != digest]
    integrity = _integrity(source / "vla.db")
    if problems or integrity != "ok":
        raise SystemExit(f"backup verification failed: checksum mismatches={problems}, integrity={integrity}")
    return manifest


def restore(source: Path, db: Path, docs: Path, force: bool) -> dict:
    manifest = verify(source)
    if (db.exists() or docs.exists()) and not force:
        raise SystemExit("target exists; stop the API and pass --force to overwrite")
    db.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    tmp = db.with_suffix(".restoring")
    shutil.copyfile(source / "vla.db", tmp)
    tmp.replace(db)
    if docs.exists():
        shutil.rmtree(docs)
    if (source / "documents").is_dir():
        shutil.copytree(source / "documents", docs)
    restored_counts = _table_counts(db)
    if restored_counts != manifest["table_counts"] or _integrity(db) != "ok":
        raise SystemExit(f"post-restore check failed: {restored_counts} != {manifest['table_counts']}")
    return {"restored_from": str(source), "table_counts": restored_counts}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.ops.backup")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--db", type=Path, default=Path("data/vla.db"))
    b.add_argument("--docs", type=Path, default=Path("data/documents"))
    b.add_argument("--out", type=Path, default=Path("backups"))
    v = sub.add_parser("verify")
    v.add_argument("--from", dest="source", type=Path, required=True)
    r = sub.add_parser("restore")
    r.add_argument("--from", dest="source", type=Path, required=True)
    r.add_argument("--db", type=Path, default=Path("data/vla.db"))
    r.add_argument("--docs", type=Path, default=Path("data/documents"))
    r.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "backup":
        print(json.dumps({"backup": str(backup(args.db, args.docs, args.out))}))
    elif args.cmd == "verify":
        print(json.dumps({"verified": str(args.source), "table_counts": verify(args.source)["table_counts"]}))
    else:
        print(json.dumps(restore(args.source, args.db, args.docs, args.force)))


if __name__ == "__main__":
    main(sys.argv[1:])
