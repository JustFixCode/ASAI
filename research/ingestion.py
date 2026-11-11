"""Offline, fail-closed capture of caller-supplied untrusted research evidence.

This module deliberately performs no network access, URL retrieval, command execution,
policy mutation, model training, broker activity, or database work. Captured text is
inert evidence only: it may contain prompt injection or instructions and must never be
interpreted or acted upon. Secret detection is heuristic (including a few common GitHub
and Bearer-token forms), not a guarantee that all secrets are found.

Research history is plaintext, unencrypted JSONL. The store creates and requires a
0600 owner-only regular file, but that filesystem permission is not confidentiality
against privileged users, host or backup operators, filesystem snapshots, or backups.
Do not treat heuristic secret scanning as a substitute for encryption, access controls,
or avoiding secrets in captured research.

The local JSONL hash chain helps this reader detect malformed or changed history that
is present. It is not tamper-proof: a valid-prefix truncation or rollback cannot be
detected. Therefore this history cannot serve as an audit log, completeness evidence,
or reconciliation source. ``captured_at`` is an untrusted caller assertion, not a
temporal authority or proof of when anything was captured.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

MAX_DOCUMENT_BYTES = 65_536
MAX_RECORD_BYTES = 131_072
MAX_STORE_BYTES = 1_048_576
MAX_RECORDS = 10_000
_OWNER_MODE = 0o600
_RECORD_TYPE = "untrusted_research_capture_no_risk_authority"
_SOURCE_KINDS = frozenset({"manual_external_research", "user_supplied_research", "local_research_note"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_SECRET = re.compile(
    r"(?:api[_ -]?key|secret|password|credential|authorization|private[_ -]?key|access[_ -]?token)\s*[:=]"
    r"|(?:AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{36})"
    r"|(?:\bbearer[ \t]+[A-Za-z0-9._~+/-]{16,}={0,2}\b)",
    re.I,
)

class ResearchIngestionError(ValueError):
    """Raised when input or local history is unsafe, malformed, or out of bounds."""

@dataclass(frozen=True)
class SourceProvenance:
    """Caller metadata, never a network instruction or temporal authority."""
    source_id: str
    source_kind: str
    source_label: str
    source_reference: str
    captured_at: str

@dataclass(frozen=True)
class ResearchDocument:
    """Immutable, explicitly untrusted text with no risk or execution authority."""
    schema_version: int
    record_type: str
    untrusted: bool
    risk_authority: bool
    provenance: SourceProvenance
    title: str
    text: str
    content_sha256: str

@dataclass(frozen=True)
class VersionedResearchRecord:
    """One immutable local-history version; the hash chain is not tamper-proof."""
    version: int
    document: ResearchDocument
    previous_record_sha256: str | None
    record_sha256: str

def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

def _text(value: object, label: str, maximum: int, *, multiline: bool = False, reject_url: bool = False) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > maximum:
        raise ResearchIngestionError(f"{label} must be nonempty bounded text")
    if "\x00" in value or (not multiline and ("\n" in value or "\r" in value)):
        raise ResearchIngestionError(f"{label} contains prohibited control characters")
    if _SECRET.search(value):
        raise ResearchIngestionError(f"{label} appears to contain an obvious credential")
    if reject_url and _URL.search(value):
        raise ResearchIngestionError(f"{label} must not be a URL or endpoint")
    return value

def _timestamp(value: object) -> str:
    if type(value) is not str or len(value) > 40:
        raise ResearchIngestionError("captured_at must be canonical ISO-8601 UTC")
    try: parsed = datetime.fromisoformat(value)
    except ValueError as exc: raise ResearchIngestionError("captured_at must be canonical ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0) or parsed.isoformat() != value:
        raise ResearchIngestionError("captured_at must be canonical ISO-8601 UTC")
    return value

def _payload(document: ResearchDocument) -> dict[str, Any]:
    return {"schema_version": document.schema_version, "record_type": document.record_type,
            "untrusted": document.untrusted, "risk_authority": document.risk_authority,
            "provenance": asdict(document.provenance), "title": document.title, "text": document.text}

def _validate_document(document: object) -> ResearchDocument:
    if type(document) is not ResearchDocument: raise ResearchIngestionError("document has an invalid type")
    if type(document.schema_version) is not int or document.schema_version != 1 or document.record_type != _RECORD_TYPE: raise ResearchIngestionError("document has an invalid schema")
    if type(document.untrusted) is not bool or type(document.risk_authority) is not bool or document.untrusted is not True or document.risk_authority is not False: raise ResearchIngestionError("research documents must remain untrusted and non-authoritative")
    p = document.provenance
    if type(p) is not SourceProvenance or type(p.source_id) is not str or not _IDENTIFIER.fullmatch(p.source_id) or _SECRET.search(p.source_id): raise ResearchIngestionError("source_id must be a bounded non-credential identifier")
    if type(p.source_kind) is not str or p.source_kind not in _SOURCE_KINDS: raise ResearchIngestionError("source_kind is not permitted")
    _text(p.source_label, "source_label", 256); _text(p.source_reference, "source_reference", 512, reject_url=True); _timestamp(p.captured_at)
    _text(document.title, "title", 512); _text(document.text, "text", MAX_DOCUMENT_BYTES, multiline=True)
    if type(document.content_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", document.content_sha256): raise ResearchIngestionError("document has an invalid content digest")
    encoded = _canonical(_payload(document)).encode()
    if len(encoded) > MAX_DOCUMENT_BYTES: raise ResearchIngestionError("document exceeds prototype size limit")
    if sha256(encoded).hexdigest() != document.content_sha256: raise ResearchIngestionError("document content digest does not match")
    return document

def capture_document(value: Mapping[str, Any]) -> ResearchDocument:
    """Validate exact fields into immutable inert evidence; no content is executed or fetched."""
    if type(value) is not dict or set(value) != {"schema_version", "provenance", "title", "text"}: raise ResearchIngestionError("document has missing or unsupported fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1: raise ResearchIngestionError("schema_version must be 1")
    source = value["provenance"]
    required = {"source_id", "source_kind", "source_label", "source_reference", "captured_at"}
    if type(source) is not dict or set(source) != required: raise ResearchIngestionError("provenance has missing or unsupported fields")
    p = SourceProvenance(source["source_id"], source["source_kind"], source["source_label"], source["source_reference"], source["captured_at"])
    provisional = ResearchDocument(1, _RECORD_TYPE, True, False, p, value["title"], value["text"], "0" * 64)
    # Validation checks all types and safety boundaries before calculating the digest.
    _validate_document(provisional) if False else None
    # validate a real digest-bearing copy; static fields above remain fixed by construction.
    raw = _payload(provisional); digest = sha256(_canonical(raw).encode()).hexdigest()
    return _validate_document(ResearchDocument(1, _RECORD_TYPE, True, False, p, value["title"], value["text"], digest))

def document_digest(document: ResearchDocument) -> str:
    """Return the stable digest that binds content to provenance."""
    return _validate_document(document).content_sha256

def _record_digest(version: int, document: ResearchDocument, previous: str | None) -> str:
    return sha256(_canonical({"version": version, "document": asdict(document), "previous_record_sha256": previous}).encode()).hexdigest()

def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchIngestionError("research history contains duplicate JSON fields")
        result[key] = value
    return result

def _safe_stat(st: os.stat_result) -> None:
    if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.geteuid()
            or stat.S_IMODE(st.st_mode) != _OWNER_MODE or st.st_size > MAX_STORE_BYTES):
        raise ResearchIngestionError("research history is not a bounded private unlinked regular file")

def _require_secure_openat() -> None:
    """Require primitives needed to resolve every path component without symlinks."""
    required = ("O_NOFOLLOW", "O_DIRECTORY")
    if (any(not isinstance(getattr(os, name, None), int) for name in required)
            or os.open not in os.supports_dir_fd
            or os.stat not in os.supports_dir_fd
            or os.stat not in os.supports_follow_symlinks):
        raise ResearchIngestionError("secure openat traversal support is required")

def _open_parent(path: Path) -> tuple[int, str]:
    """Open each parent through directory fds; never resolve an intermediate symlink."""
    _require_secure_openat()
    parts = path.parts
    if not parts or path.name in {"", ".", ".."} or any(part in {"", ".", ".."} for part in parts):
        raise ResearchIngestionError("history path must not contain traversal components")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        if path.is_absolute():
            fd = os.open(path.anchor, directory_flags)
            components = parts[1:-1]
        else:
            fd = os.open(".", directory_flags)
            components = parts[:-1]
        try:
            for component in components:
                child = os.open(component, directory_flags, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise
    except ResearchIngestionError:
        raise
    except OSError as exc:
        raise ResearchIngestionError("history parent cannot be opened safely") from exc

def _open(path: Path, writable: bool) -> int:
    parent_fd, leaf = _open_parent(path)
    flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        created = False
        try: before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            if not writable: raise
            fd = os.open(leaf, flags | os.O_CREAT | os.O_EXCL, _OWNER_MODE, dir_fd=parent_fd)
            created = True
        else:
            if not stat.S_ISREG(before.st_mode): raise ResearchIngestionError("research history must be a regular file")
            fd = os.open(leaf, flags, dir_fd=parent_fd)
        try:
            # Existing files must already meet every private-file requirement. This
            # avoids changing an unsafe inode before rejecting it.
            if writable and created: os.fchmod(fd, _OWNER_MODE)
            _safe_stat(os.fstat(fd)); return fd
        except BaseException: os.close(fd); raise
    except (ResearchIngestionError, FileNotFoundError): raise
    except OSError as exc: raise ResearchIngestionError("research history cannot be opened safely") from exc
    finally:
        os.close(parent_fd)

def _read_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET); chunks=[]; total=0
    while True:
        part=os.read(fd, min(65536, MAX_STORE_BYTES + 1 - total))
        if not part: break
        chunks.append(part); total += len(part)
        if total > MAX_STORE_BYTES: raise ResearchIngestionError("research history exceeds prototype size limit")
    return b"".join(chunks)

def _decode(item: object, version: int, previous: str | None) -> VersionedResearchRecord:
    if type(item) is not dict or set(item) != {"version","document","previous_record_sha256","record_sha256"} or type(item["version"]) is not int or item["version"] != version or item["previous_record_sha256"] != previous: raise ResearchIngestionError("research history sequence is invalid")
    d=item["document"]
    if type(d) is not dict or set(d) != {"schema_version","record_type","untrusted","risk_authority","provenance","title","text","content_sha256"} or type(d["provenance"]) is not dict: raise ResearchIngestionError("research history contains an invalid document")
    try: doc=ResearchDocument(d["schema_version"],d["record_type"],d["untrusted"],d["risk_authority"],SourceProvenance(**d["provenance"]),d["title"],d["text"],d["content_sha256"])
    except (TypeError, KeyError) as exc: raise ResearchIngestionError("research history contains an invalid document") from exc
    _validate_document(doc); record=VersionedResearchRecord(version,doc,previous,item["record_sha256"])
    if type(record.record_sha256) is not str or record.record_sha256 != _record_digest(version,doc,previous): raise ResearchIngestionError("research history integrity check failed")
    return record

class ResearchStore:
    """Private bounded history, not an audit, completeness, or reconciliation record.

    A valid-prefix truncation or rollback cannot be detected even when every remaining
    record validates, so this history is not temporal evidence.
    """
    def __init__(self, path: str | Path) -> None:
        if type(path) is not str and not isinstance(path, Path): raise ResearchIngestionError("history path has an invalid type")
        self.path=Path(path)
        if self.path.name in {"", ".", ".."}: raise ResearchIngestionError("a concrete local history file is required")
    def _read_locked(self, fd: int) -> list[VersionedResearchRecord]:
        _safe_stat(os.fstat(fd)); raw=_read_all(fd)
        if not raw: return []
        if not raw.endswith(b"\n"): raise ResearchIngestionError("research history has a partial record")
        try: lines=raw[:-1].decode("utf-8").split("\n")
        except UnicodeDecodeError as exc: raise ResearchIngestionError("research history cannot be decoded") from exc
        if len(lines)>MAX_RECORDS: raise ResearchIngestionError("research history exceeds record limit")
        records=[]; previous=None; seen_documents: set[str] = set()
        for v,line in enumerate(lines,1):
            if not line or len(line.encode())>MAX_RECORD_BYTES: raise ResearchIngestionError("research history record is invalid")
            try: record=_decode(json.loads(line, object_pairs_hook=_reject_duplicate_json_keys),v,previous)
            except json.JSONDecodeError as exc: raise ResearchIngestionError("research history contains invalid JSON") from exc
            if record.document.content_sha256 in seen_documents:
                raise ResearchIngestionError("research history contains a duplicate document")
            seen_documents.add(record.document.content_sha256)
            records.append(record); previous=record.record_sha256
        return records
    def _lock(self, fd: int, exclusive: bool) -> None:
        try:
            import fcntl; fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        except (ImportError,OSError) as exc: raise ResearchIngestionError("safe file locking is unavailable") from exc
    def history(self) -> list[VersionedResearchRecord]:
        try: fd=_open(self.path,False)
        except FileNotFoundError: return []
        try:
            self._lock(fd,False)
            # Check the opened inode after locking, not only during path resolution.
            _safe_stat(os.fstat(fd))
            return self._read_locked(fd)
        finally:
            try:
                import fcntl; fcntl.flock(fd,fcntl.LOCK_UN)
            finally: os.close(fd)
    def record(self, document: ResearchDocument) -> VersionedResearchRecord:
        _validate_document(document)
        # Parents are never created; _open traverses each existing component by fd.
        fd=_open(self.path,True)
        try:
            self._lock(fd,True)
            # Check the opened inode after locking, not only during path resolution.
            _safe_stat(os.fstat(fd))
            records=self._read_locked(fd)
            if any(item.document.content_sha256 == document.content_sha256 for item in records):
                raise ResearchIngestionError("duplicate research document is not permitted")
            previous=records[-1].record_sha256 if records else None; version=len(records)+1
            record=VersionedResearchRecord(version,document,previous,_record_digest(version,document,previous))
            encoded=(_canonical({"version":version,"document":asdict(document),"previous_record_sha256":previous,"record_sha256":record.record_sha256})+"\n").encode()
            # Revalidate immediately before mutating in case another process linked it.
            _safe_stat(os.fstat(fd)); original=os.fstat(fd).st_size
            if len(encoded)>MAX_RECORD_BYTES or original+len(encoded)>MAX_STORE_BYTES or version>MAX_RECORDS: raise ResearchIngestionError("research history would exceed prototype size limit")
            os.lseek(fd,0,os.SEEK_END)
            try:
                sent=0
                while sent<len(encoded):
                    n=os.write(fd,encoded[sent:])
                    if type(n) is not int or n<=0: raise OSError("short write")
                    sent+=n
                os.fsync(fd)
            except OSError as exc:
                try: os.ftruncate(fd,original); os.fsync(fd)
                except OSError: pass
                raise ResearchIngestionError("research history write failed and was rolled back where possible") from exc
            return record
        finally:
            try:
                import fcntl; fcntl.flock(fd,fcntl.LOCK_UN)
            finally: os.close(fd)
