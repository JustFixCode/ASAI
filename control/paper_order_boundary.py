"""Fail-closed paper-order decision boundary.

This module deliberately has *no* broker, credential, network, or persistence
capability. It creates a deterministic fingerprint of a decision only after an
independent reconciliation/preflight diagnostic has passed. The fingerprint
creates no authority and does not provide durable idempotency or time
enforcement. Dispatch is always disabled: an application must implement the
matching PostgreSQL transaction and an independently authenticated
broker-evidence collector before it can submit.

The in-process registry below is intentionally NOT presented as durable
idempotency or a concurrency control.  It is useful as a final integration
tripwire and for tests, but process restart/failover loses it; therefore every
``dispatch`` attempt fails closed.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from threading import Lock
from typing import Final

from .preflight import (CanonicalCommand, ControlPolicy, MarketMark,
                        PreflightDiagnostic, preflight)
from reconciliation import TradingSnapshot

_MAX_AGE: Final[timedelta] = timedelta(seconds=30)

@dataclass(frozen=True, slots=True)
class BoundPaperDecision:
    request_id: str
    account_id: str
    client_order_id: str
    binding: str
    decided_at: datetime
    expires_at: datetime
    diagnostic: PreflightDiagnostic

class PaperOrderBoundary:
    """Planning-only fingerprint helper; no authority or durable enforcement."""
    def __init__(self) -> None:
        self._used: set[str] = set()
        self._lock = Lock()

    @staticmethod
    def _text(value: object) -> bool:
        return isinstance(value, str) and bool(value) and value == value.strip() and len(value) <= 128 and value.isprintable()

    @staticmethod
    def _time(value: object) -> bool:
        return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None

    @staticmethod
    def _binding(request_id: str, account_id: str, client_order_id: str, diagnostic: PreflightDiagnostic, now: datetime) -> str:
        # diagnostic fingerprint commits exact policy, command, marks, account evidence and flags.
        payload = json.dumps({"request_id": request_id, "account_id": account_id,
            "client_order_id": client_order_id, "preflight": diagnostic.fingerprint,
            "decided_at": now.astimezone(timezone.utc).isoformat()}, sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()

    def decide(self, *, request_id: str, client_order_id: str, policy: ControlPolicy,
               command: CanonicalCommand, broker: TradingSnapshot, internal: TradingSnapshot,
               mark: MarketMark, latch_engaged: bool, trading_disabled: bool,
               now: datetime) -> BoundPaperDecision:
        """Consume a request id and create an unexecutable fingerprinted decision.

        The caller must provide independently collected broker/internal evidence;
        this boundary cannot establish authority, durable idempotency, or time
        enforcement, and refuses malformed input.
        """
        if not self._text(request_id) or not self._text(client_order_id) or not self._time(now):
            raise ValueError("invalid request identity or decision time")
        # Reserve before evaluation: failures are intentionally consumed to prevent
        # a caller from racing altered evidence under a reused id.
        with self._lock:
            if request_id in self._used:
                raise ValueError("request id has already been consumed")
            self._used.add(request_id)
        diagnostic = preflight(policy, command, broker, internal, mark,
                               latch_engaged=latch_engaged,
                               trading_disabled=trading_disabled, now=now)
        if not diagnostic.passed or diagnostic.fingerprint is None:
            raise PermissionError("paper-order preflight did not pass")
        if broker.metadata.account_id != policy.expected_account_id:
            raise PermissionError("account binding failed")
        return BoundPaperDecision(request_id, policy.expected_account_id, client_order_id,
            self._binding(request_id, policy.expected_account_id, client_order_id, diagnostic, now),
            now, now + _MAX_AGE, diagnostic)

    def dispatch(self, decision: BoundPaperDecision, *, now: datetime) -> None:
        """Always deny: no runtime public method can create broker orders."""
        if not isinstance(decision, BoundPaperDecision) or not self._time(now):
            raise PermissionError("invalid dispatch decision")
        raise PermissionError("broker dispatch unavailable: durable authoritative transaction is not implemented")

__all__ = ["BoundPaperDecision", "PaperOrderBoundary"]
