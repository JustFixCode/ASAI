"""Fail-closed loader for a deliberately small JSON-compatible YAML subset.

JSON is valid YAML, so manifests use JSON syntax in ``.yaml`` files.  Parsing
JSON only avoids adding a YAML dependency and rejects YAML features such as
anchors, tags, aliases, and implicit type coercion.  This module performs no
network I/O and contains no credential loading or execution capability.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

MAX_MANIFEST_BYTES = 16_384


class ConfigurationError(ValueError):
    """A manifest is malformed, unsafe, or outside the narrow prototype schema."""


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("duplicate configuration key")
        result[key] = value
    return result


def _require_exact_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ConfigurationError(f"{label} has missing or unknown fields")
    return value


def _require(value: object, expected: object, label: str) -> None:
    # Exact type checks deliberately reject truthy strings and integer booleans.
    if type(expected) is bool:
        valid = type(value) is bool and value is expected
    else:
        valid = value == expected and type(value) is type(expected)
    if not valid:
        raise ConfigurationError(f"{label} must be {expected!r}")


def normalize_manifest(value: object) -> dict[str, Any]:
    """Validate and return only the safe, canonical manifest fields.

    The schema intentionally has no credential, URL, host, symbol, order, or
    strategy fields.  Any extension is rejected rather than silently retained.
    """
    root = _require_exact_keys(value, {"schema_version", "market_data", "broker", "memory"}, "manifest")
    _require(root["schema_version"], 1, "schema_version")

    market_data = _require_exact_keys(
        root["market_data"],
        {"provider", "retrieval_enabled", "live_data_enabled", "network_enabled"},
        "market_data",
    )
    _require(market_data["provider"], "unconfigured", "market_data.provider")
    _require(market_data["retrieval_enabled"], False, "market_data.retrieval_enabled")
    _require(market_data["live_data_enabled"], False, "market_data.live_data_enabled")
    _require(market_data["network_enabled"], False, "market_data.network_enabled")

    broker = _require_exact_keys(
        root["broker"],
        {"provider", "mode", "live_trading_enabled", "execution_enabled", "submission_enabled"},
        "broker",
    )
    _require(broker["provider"], "alpaca", "broker.provider")
    _require(broker["mode"], "paper", "broker.mode")
    _require(broker["live_trading_enabled"], False, "broker.live_trading_enabled")
    _require(broker["execution_enabled"], False, "broker.execution_enabled")
    _require(broker["submission_enabled"], False, "broker.submission_enabled")

    memory = _require_exact_keys(
        root["memory"],
        {"purpose", "store", "autonomous_updates_enabled", "human_review_required"},
        "memory",
    )
    _require(memory["purpose"], "configuration_audit_history", "memory.purpose")
    _require(memory["store"], "local_jsonl", "memory.store")
    _require(memory["autonomous_updates_enabled"], False, "memory.autonomous_updates_enabled")
    _require(memory["human_review_required"], True, "memory.human_review_required")

    # Reconstruct rather than returning caller-owned dictionaries, so unknown or
    # sensitive input is never retained by downstream persistence.
    return {
        "schema_version": 1,
        "market_data": dict(market_data),
        "broker": dict(broker),
        "memory": dict(memory),
    }


def _read_manifest_file(path: Path) -> bytes:
    """Open one regular file without following its final path component."""
    try:
        # Avoid blocking on a FIFO before opening it.  The fstat below closes the
        # lstat/open race and is the authority for the opened descriptor.
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise ConfigurationError("manifest must be a regular file")
        if not hasattr(os, "O_NOFOLLOW"):
            raise ConfigurationError("manifest requires no-follow file support")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
        fd = os.open(path, flags)
    except ConfigurationError:
        raise
    except OSError as exc:
        raise ConfigurationError("manifest cannot be read") from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ConfigurationError("manifest must be a regular file")
        if not 0 < file_stat.st_size <= MAX_MANIFEST_BYTES:
            raise ConfigurationError("manifest size is outside allowed bounds")
        # Reading one byte beyond the cap detects a concurrent enlargement and
        # bounds memory consumption even if the size changes after fstat.
        raw = os.read(fd, MAX_MANIFEST_BYTES + 1)
        if not 0 < len(raw) <= MAX_MANIFEST_BYTES:
            raise ConfigurationError("manifest size is outside allowed bounds")
        if os.read(fd, 1):
            raise ConfigurationError("manifest size is outside allowed bounds")
        return raw
    except OSError as exc:
        raise ConfigurationError("manifest cannot be read") from exc
    finally:
        os.close(fd)


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load a bounded JSON-compatible YAML manifest without network access."""
    raw = _read_manifest_file(Path(path))
    try:
        decoded = raw.decode("utf-8")
        parsed = json.loads(decoded, object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError("manifest must be strict JSON-compatible YAML") from exc
    return normalize_manifest(parsed)


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Return a stable digest for an already validated manifest."""
    normalized = normalize_manifest(dict(manifest))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()
