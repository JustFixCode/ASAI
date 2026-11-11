"""Offline, text-only capture of explicitly untrusted trading research.

This package is deliberately not a market-data connector, model-training system,
risk authority, trade signal, order mechanism, or PostgreSQL persistence layer.
"""

from .ingestion import (
    MAX_DOCUMENT_BYTES,
    MAX_RECORDS,
    ResearchDocument,
    ResearchIngestionError,
    ResearchStore,
    SourceProvenance,
    VersionedResearchRecord,
    capture_document,
    document_digest,
)

__all__ = [
    "MAX_DOCUMENT_BYTES",
    "MAX_RECORDS",
    "ResearchDocument",
    "ResearchIngestionError",
    "ResearchStore",
    "SourceProvenance",
    "VersionedResearchRecord",
    "capture_document",
    "document_digest",
]
