"""Backup/restore round trip: data written after a backup is gone after restore; checksums catch tampering."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.ops import backup as ops


def _db(path: Path, rows: int, extra: str | None = None) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO applications VALUES (?)", [(f"a{i}",) for i in range(rows)])
        if extra:
            conn.execute("INSERT INTO applications VALUES (?)", (extra,))
        conn.commit()


def test_backup_restore_round_trip(tmp_path: Path) -> None:
    db, docs = tmp_path / "live" / "vla.db", tmp_path / "live" / "documents"
    db.parent.mkdir()
    _db(db, 3)
    (docs / "t-northwind").mkdir(parents=True)
    (docs / "t-northwind" / ("a" * 64)).write_bytes(b"%PDF-1.7 original")

    snapshot = ops.backup(db, docs, tmp_path / "backups")
    assert ops.verify(snapshot)["table_counts"] == {"applications": 3}

    _db(db, 0, extra="after-backup")
    (docs / "t-northwind" / ("a" * 64)).write_bytes(b"corrupted")

    with pytest.raises(SystemExit):
        ops.restore(snapshot, db, docs, force=False)
    result = ops.restore(snapshot, db, docs, force=True)
    assert result["table_counts"] == {"applications": 3}
    assert (docs / "t-northwind" / ("a" * 64)).read_bytes() == b"%PDF-1.7 original"


def test_verify_detects_tampering(tmp_path: Path) -> None:
    db = tmp_path / "vla.db"
    _db(db, 1)
    snapshot = ops.backup(db, tmp_path / "missing-docs", tmp_path / "backups")
    _db(snapshot / "vla.db", 0, extra="tampered")
    with pytest.raises(SystemExit, match="verification failed"):
        ops.verify(snapshot)
