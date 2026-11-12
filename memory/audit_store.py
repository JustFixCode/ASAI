"""Local configuration-audit history for validated configuration only.

This is a single-machine JSONL audit helper, not a shared database, PostgreSQL
system of record, model-memory system, or autonomous learning/update mechanism.
It never loads credentials, performs network activity, or enables execution.

The local file is *not tamper-evident*: a sufficiently privileged local actor
can deliberately truncate, rewrite, or replace it, and this helper cannot
detect that.  A crash that leaves a partial JSONL line is rejected fail-closed
and requires manual investigation/intervention; it is not repaired silently.
Consequently this module does not claim durable audit integrity.  It is only a
bounded, permission-checked local review aid.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from config.manifest import ConfigurationError, manifest_digest, normalize_manifest

MAX_HISTORY_BYTES = 1_048_576
MAX_RECORDS = 10_000
_OWNER_MODE = 0o600


class MemoryError(RuntimeError):
    """The local audit store cannot safely read or append history."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _require_safe_history_stat(file_stat: os.stat_result) -> None:
    """Require the opened history descriptor to be private, regular, and ours."""
    if not stat.S_ISREG(file_stat.st_mode):
        raise MemoryError("audit history must be a regular file")
    if file_stat.st_uid != os.geteuid():
        raise MemoryError("audit history must be owned by the current user")
    if stat.S_IMODE(file_stat.st_mode) != _OWNER_MODE:
        raise MemoryError("audit history permissions must be exactly 0600")
    if file_stat.st_size > MAX_HISTORY_BYTES:
        raise MemoryError("audit history exceeds local prototype size limit")


def _open_history(path: Path, *, writable: bool) -> int:
    """Open a history file without following symlinks, creating it as 0600 only."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise MemoryError("audit history requires no-follow file support")
    flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        try:
            # lstat rejects FIFOs/devices before open, avoiding a FIFO read/open
            # block.  fstat after open closes the lstat/open race.
            path_stat = os.lstat(path)
        except FileNotFoundError:
            if not writable:
                raise
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, _OWNER_MODE)
            try:
                os.fchmod(fd, _OWNER_MODE)  # umask may only make this stricter.
                _require_safe_history_stat(os.fstat(fd))
                return fd
            except BaseException:
                os.close(fd)
                raise
        if not stat.S_ISREG(path_stat.st_mode):
            raise MemoryError("audit history must be a regular file")
        fd = os.open(path, flags)
        try:
            _require_safe_history_stat(os.fstat(fd))
            return fd
        except BaseException:
            os.close(fd)
            raise
    except MemoryError:
        raise
    except FileNotFoundError:
        # Readers use this to distinguish a genuinely absent history from an
        # unsafe existing path; writers create atomically above.
        raise
    except OSError as exc:
        raise MemoryError("audit history cannot be opened safely") from exc


def _validate_timestamp(value: object) -> str:
    if type(value) is not str or not value or len(value) > 40:
        raise MemoryError("audit history contains an invalid timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MemoryError("audit history contains an invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0) or parsed.isoformat() != value:
        raise MemoryError("audit history timestamp must be canonical ISO-8601 UTC")
    return value


def _decode_records(raw: bytes) -> list[dict[str, Any]]:
    if len(raw) > MAX_HISTORY_BYTES:
        raise MemoryError("audit history exceeds local prototype size limit")
    if not raw:
        return []
    # A nonempty JSONL log must terminate each complete record.  In particular,
    # this rejects a crash-interrupted final append instead of guessing at repair.
    if not raw.endswith(b"\n"):
        raise MemoryError("audit history has a partial record; manual intervention is required")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise MemoryError("audit history cannot be read safely") from exc
    records: list[dict[str, Any]] = []
    try:
        for line in lines:
            if not line:
                raise MemoryError("audit history contains an invalid record")
            item = json.loads(line)
            if type(item) is not dict or set(item) != {"version", "recorded_at", "digest", "configuration"}:
                raise MemoryError("audit history contains an invalid record")
            if type(item["version"]) is not int or item["version"] < 1:
                raise MemoryError("audit history contains an invalid version")
            timestamp = _validate_timestamp(item["recorded_at"])
            config = normalize_manifest(item["configuration"])
            if type(item["digest"]) is not str or item["digest"] != manifest_digest(config):
                raise MemoryError("audit history contains an invalid digest")
            records.append({"version": item["version"], "recorded_at": timestamp, "digest": item["digest"], "configuration": config})
    except (json.JSONDecodeError, ConfigurationError) as exc:
        raise MemoryError("audit history contains an invalid record") from exc
    if len(records) > MAX_RECORDS or [r["version"] for r in records] != list(range(1, len(records) + 1)):
        raise MemoryError("audit history is not a bounded sequential log")
    return records


def _read_locked_history(fd: int, fcntl: Any) -> list[dict[str, Any]]:
    """Read the already-open, locked descriptor with a strict byte cap."""
    _require_safe_history_stat(os.fstat(fd))
    os.lseek(fd, 0, os.SEEK_SET)
    raw = bytearray()
    while len(raw) <= MAX_HISTORY_BYTES:
        chunk = os.read(fd, min(65_536, MAX_HISTORY_BYTES + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
    if len(raw) > MAX_HISTORY_BYTES:
        raise MemoryError("audit history exceeds local prototype size limit")
    return _decode_records(bytes(raw))


class AuditStore:
    """Append validated configuration snapshots to a local review-only JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.name in {"", ".", ".."}:
            raise MemoryError("a concrete local audit file is required")

    def history(self) -> list[dict[str, Any]]:
        """Return validated snapshots under a shared advisory lock."""
        try:
            import fcntl  # Unix-only; this prototype intentionally fails closed elsewhere.
            try:
                fd = _open_history(self.path, writable=False)
            except FileNotFoundError:
                return []
            try:
                fcntl.flock(fd, fcntl.LOCK_SH)
                try:
                    return _read_locked_history(fd, fcntl)
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        except (OSError, ImportError) as exc:
            raise MemoryError("audit history cannot be read safely") from exc

    def record(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Append a normalized snapshot under an exclusive POSIX advisory lock."""
        try:
            normalized = normalize_manifest(dict(manifest))
        except (TypeError, ConfigurationError) as exc:
            raise MemoryError("only a validated safe manifest can be recorded") from exc
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            import fcntl  # Unix-only; this prototype intentionally fails closed elsewhere.
            fd = _open_history(self.path, writable=True)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    records = _read_locked_history(fd, fcntl)
                    record = {
                        "version": len(records) + 1,
                        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                        "digest": manifest_digest(normalized),
                        "configuration": normalized,
                    }
                    encoded = (_canonical(record) + "\n").encode("utf-8")
                    file_stat = os.fstat(fd)
                    _require_safe_history_stat(file_stat)
                    if file_stat.st_size + len(encoded) > MAX_HISTORY_BYTES:
                        raise MemoryError("audit history would exceed local prototype size limit")
                    os.lseek(fd, 0, os.SEEK_END)
                    total = 0
                    while total < len(encoded):
                        written = os.write(fd, encoded[total:])
                        if written <= 0:
                            raise MemoryError("audit history cannot be safely persisted")
                        total += written
                    os.fsync(fd)
                    return record
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        except (OSError, ImportError) as exc:
            raise MemoryError("audit history cannot be safely persisted") from exc
