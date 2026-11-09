"""Content-addressed original-document storage. Local filesystem now; S3 (SSE-KMS) implements the same port."""

import re
from pathlib import Path
from typing import Protocol

_TENANT = re.compile(r"^[A-Za-z0-9\-]{1,64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DocumentStore(Protocol):
    def put(self, tenant_id: str, sha256: str, data: bytes) -> str: ...

    def get(self, key: str) -> bytes: ...


class LocalDocumentStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        tenant_id, _, digest = key.partition("/")
        # Keys are built only from validated ids, so no client-supplied text reaches the filesystem path.
        if not _TENANT.match(tenant_id) or not _SHA256.match(digest):
            raise ValueError("invalid storage key")
        return self._root / tenant_id / digest

    def put(self, tenant_id: str, sha256: str, data: bytes) -> str:
        key = f"{tenant_id}/{sha256}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()
