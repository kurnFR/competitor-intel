"""Durable raw-document storage abstraction.

The default backend is local filesystem storage so development does not require
an external object-storage service. The interface is intentionally backend-neutral
so S3/MinIO can be added later without changing crawler or document models.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class StoredObject:
    uri: str
    sha256: str
    size_bytes: int
    content_type: str


class RawDocumentStore:
    def put(self, content: bytes, content_type: str, source_id: str, extension: str = "bin") -> StoredObject:
        raise NotImplementedError

    def get(self, uri: str) -> bytes:
        raise NotImplementedError


class LocalRawDocumentStore(RawDocumentStore):
    """Content-addressed local store suitable for development and single-host use."""

    def __init__(self, root: str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, content_type: str, source_id: str, extension: str = "bin") -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        safe_source = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(source_id))
        safe_ext = "".join(c for c in extension.lower().lstrip(".") if c.isalnum()) or "bin"
        relative = Path(safe_source) / digest[:2] / f"{digest}.{safe_ext}"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(content)
            os.replace(temporary, path)
        return StoredObject(
            uri=f"file://{path}",
            sha256=digest,
            size_bytes=len(content),
            content_type=content_type,
        )

    def get(self, uri: str) -> bytes:
        if not uri.startswith("file://"):
            raise ValueError("LocalRawDocumentStore only supports file:// URIs")
        return Path(uri[7:]).read_bytes()


def get_raw_document_store(root: Optional[str] = None) -> RawDocumentStore:
    configured = root or os.getenv("RAW_DOCUMENT_STORAGE_PATH", "./data/raw_documents")
    return LocalRawDocumentStore(configured)
