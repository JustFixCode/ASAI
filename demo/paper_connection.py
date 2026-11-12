"""Explicit, read-only Alpaca paper account connection check.

Run ``python -m demo.paper_connection`` after setting APCA_API_KEY_ID and
APCA_API_SECRET_KEY in the environment. Optionally set
APCA_EXPECTED_ACCOUNT_ID to the expected account UUID. No credentials or
account identifiers are printed. This module is independent of the simulator.
Importing it does not read credentials or connect to the network.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hmac
import http.client
import json
import os
import re
import subprocess
import sys

_HOST = "paper-api.alpaca.markets"
_PATH = "/v2/account"
_SOCKET_TIMEOUT = 5.0
_DEADLINE = 10.0
_MAX_BODY = 65536
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
_STATUSES = frozenset({
    "INACTIVE", "ONBOARDING", "SUBMITTED", "RESUBMITTED", "SUBMISSION_FAILED",
    "ACTION_REQUIRED", "EDITED", "ACCOUNT_UPDATED", "APPROVAL_PENDING",
    "REAPPROVAL_PENDING", "SIGNED_UP", "KYC_SUBMITTED", "LIMITED", "AML_REVIEW",
    "APPROVED", "REJECTED", "ACTIVE", "DISABLED", "DISABLE_PENDING",
    "ACCOUNT_CLOSED", "PAPER_ONLY",
})
_NOTICE = "Read-only paper connection check; independent of the simulator and its funds. No orders were placed."


@dataclass(frozen=True)
class CheckResult:
    """Only safe, allowlisted facts; never contains credentials or account ID."""
    connected: bool
    account_status: str | None
    identity_verified: bool
    checked_at: str


def _valid_credential(value: object) -> bool:
    # Printable non-space ASCII prevents HTTP header injection and excessive headers.
    return isinstance(value, str) and 1 <= len(value) <= 256 and all(33 <= ord(c) <= 126 for c in value)


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and _UUID.fullmatch(value) is not None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("invalid JSON constant")


def _validate_unicode(value: object) -> None:
    """Reject unpaired surrogate escapes anywhere, including object keys."""
    if isinstance(value, str):
        value.encode("utf-8", "strict")
    elif isinstance(value, list):
        for item in value:
            _validate_unicode(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_unicode(key)
            _validate_unicode(item)


def _perform_check(key: str, secret: str, expected_id: str | None) -> tuple[str, bool] | None:
    """One fixed HTTPS request, no proxy, redirects, retry or write interface.

    Run in a disposable worker so the parent can enforce an absolute deadline,
    including DNS, TLS, headers and a slowly streaming response.
    """
    connection = None
    response = None
    try:
        connection = http.client.HTTPSConnection(_HOST, timeout=_SOCKET_TIMEOUT)
        connection.request("GET", _PATH, headers={
            "Accept": "application/json",
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        })
        response = connection.getresponse()
        if response.status != 200:
            return None  # Never read error or redirect bodies, never follow Location.
        body = response.read(_MAX_BODY + 1)
        if (not isinstance(body, bytes) or len(body) > _MAX_BODY or
                (response.length is not None and response.length != 0)):
            return None
        payload = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant, parse_float=Decimal)
        _validate_unicode(payload)
        if not isinstance(payload, dict):
            return None
        account_id, status = payload.get("id"), payload.get("status")
        if not _valid_id(account_id) or not isinstance(status, str) or status not in _STATUSES:
            return None
        if expected_id is not None and not hmac.compare_digest(account_id.lower(), expected_id.lower()):
            return None
        return status, expected_id is not None
    except Exception:
        return None
    finally:
        # On Connection: close responses, HTTPConnection may already have
        # detached its socket; closing the connection alone does not close the
        # response's file/socket, especially when its body was not read.
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _subprocess_main() -> None:
    """Worker protocol: credentials on stdin; only an allowlisted result on stdout."""
    try:
        values = json.loads(sys.stdin.buffer.read(4097))
        if (not isinstance(values, list) or len(values) != 3 or
                not _valid_credential(values[0]) or not _valid_credential(values[1]) or
                (values[2] is not None and not _valid_id(values[2]))):
            return
        result = _perform_check(values[0], values[1], values[2])
        if result is not None:
            sys.stdout.write(json.dumps(result))
    except BaseException:
        pass


def _run_bounded(key: str, secret: str, expected_id: str | None) -> tuple[str, bool] | None:
    """Deadline covers DNS and slow-drip responses as well as socket operations.

    An isolated worker avoids importing a caller's main module. Credentials are
    sent only over stdin, never in command arguments or the child environment.
    stderr is discarded even if Python fails before reaching our worker.
    """
    try:
        command = [sys.executable, "-I", "-S", "-c",
                   "import runpy,sys; runpy.run_path(sys.argv[1])['_subprocess_main']()",
                   os.path.abspath(__file__)]
        data = json.dumps([key, secret, expected_id]).encode("utf-8")
        completed = subprocess.run(command, input=data, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env={}, timeout=_DEADLINE,
                                   check=False)
        if completed.returncode != 0 or len(completed.stdout) > 256:
            return None
        result = json.loads(completed.stdout)
        if (not isinstance(result, list) or len(result) != 2 or
                not isinstance(result[0], str) or result[0] not in _STATUSES or
                type(result[1]) is not bool or result[1] != (expected_id is not None)):
            return None
        return result[0], result[1]
    except Exception:
        return None


def check_paper_connection() -> CheckResult:
    """Explicitly check once, reading credentials only at invocation time.

    A successful result without APCA_EXPECTED_ACCOUNT_ID confirms access to a
    paper account, not that it is a particular account. Failures are deliberately
    indistinguishable and contain no transport or broker details.
    """
    safe = None
    try:
        key = os.environ.get("APCA_API_KEY_ID", "")
        secret = os.environ.get("APCA_API_SECRET_KEY", "")
        expected = os.environ.get("APCA_EXPECTED_ACCOUNT_ID")
        if _valid_credential(key) and _valid_credential(secret) and (expected is None or _valid_id(expected)):
            safe = _run_bounded(key, secret, expected)
    except Exception:
        safe = None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if safe is None:
        return CheckResult(False, None, False, now)
    return CheckResult(True, safe[0], safe[1], now)


def main(argv: list[str] | None = None) -> int:
    """CLI accepts no options, in particular no credential or host arguments."""
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("No command-line arguments are accepted.")
        return 2
    result = check_paper_connection()
    if result.connected:
        print("Paper connection: verified")
        print("Account status: " + result.account_status)
        print("Expected account identity: " + ("verified" if result.identity_verified else "not configured; not verified"))
    else:
        print("Paper connection: not verified")
    print("Checked at (UTC): " + result.checked_at)
    print(_NOTICE)
    return 0 if result.connected else 1


if __name__ == "__main__":
    raise SystemExit(main())
