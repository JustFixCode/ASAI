"""Opt-in PostgreSQL recorder for bounded offline research results.

The database stores a writer-supplied receipt.  It verifies the result's bounded
shape and that the two supplied input digest strings agree, but cannot recompute
or independently verify the input digest from the original input file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app import research_cli

_DSN_ENV = "ASAI_RESEARCH_POSTGRES_DSN"
_MAX_RESULT_BYTES = 1_048_576
_MAX_ITEMS = 10_000
_MAX_DECIMAL = 128
_SQL = "SELECT asai.record_research_run(%s, %s::jsonb)"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?\+00:00$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,15}$")
_RESULT_KEYS = frozenset(("mode", "simulation", "provenance", "dataset_sha256", "configuration_sha256", "input_sha256", "research_document", "trust_disclaimers"))
_SIMULATION_KEYS = frozenset(("equity", "final_cash", "final_equity", "final_position", "orders", "provenance", "status", "symbol", "warnings"))
_PROVENANCE_KEYS = frozenset(("as_of", "engine_provenance_sha256", "status"))
_DOCUMENT_KEYS = frozenset(("content_sha256", "untrusted", "risk_authority"))
_ORDER_KEYS = frozenset(("signal_timestamp", "fill_timestamp", "side", "quantity", "status", "fill_price", "fee", "reason"))
_EQUITY_KEYS = frozenset(("timestamp", "cash", "position", "close", "equity"))
_STATUSES = frozenset(("COMPLETED", "COMPLETED_WITH_REJECTIONS", "COMPLETED_WITH_UNFILLED", "COMPLETED_WITH_REJECTIONS_AND_UNFILLED"))
_ORDER_STATUS = frozenset(("FILLED", "REJECTED_INSUFFICIENT_CASH", "REJECTED_POSITION_LIMIT", "REJECTED_NEGATIVE_CASH", "UNFILLED_END_OF_DATA"))
_REASONS = {
    "FILLED": "documented next-bar open fill after closed-bar signal",
    "REJECTED_INSUFFICIENT_CASH": "cash cannot cover fill and fee",
    "REJECTED_POSITION_LIMIT": "max long position would be exceeded",
    "REJECTED_NEGATIVE_CASH": "sale would make cash negative",
    "UNFILLED_END_OF_DATA": "no next documented bar open exists for an auditable fill",
}
_GAP_WARNING = "Supplied history contains permitted inter-bar gaps; it is incomplete and does not establish continuous market coverage."
_TRUST_DISCLAIMERS = (
    "Historical bars are untrusted caller-supplied fixtures; acceptance does not establish that prices, timestamps, or history are real, complete, or suitable.",
    "The caller-supplied as_of cutoff only constrains this deterministic simulation; it does not independently verify that any bar is genuinely past, closed, timely, complete, or suitable.",
    "Results are deterministic analysis of supplied data, not a forecast, recommendation, validation of a strategy, or financial advice.",
    "No network, credentials, broker, trading, order submission, control, risk, or manifest override path is used; simulated orders are not real orders.",
    "Optional research text is captured as inert untrusted evidence only and has no execution, control, risk, or configuration authority.",
)


class ResearchPostgresError(RuntimeError):
    """Safe public failure for the opt-in research receipt path."""


def _storage_json(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise ResearchPostgresError("research result is not valid JSON") from None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _is_timestamp(value: object) -> bool:
    return type(value) is str and _TIMESTAMP.fullmatch(value) is not None


def _is_decimal(value: object) -> bool:
    return type(value) is str and len(value) <= _MAX_DECIMAL and _DECIMAL.fullmatch(value) is not None


def _invalid() -> None:
    raise ResearchPostgresError("research result is invalid")


def _validate_order(value: object) -> bool:
    if type(value) is not dict or set(value) != _ORDER_KEYS:
        return False
    status = value.get("status")
    if (not _is_timestamp(value.get("signal_timestamp")) or value.get("side") not in ("BUY", "SELL")
            or status not in _ORDER_STATUS or value.get("reason") != _REASONS.get(status)
            or not _is_decimal(value.get("quantity"))):
        return False
    unfilled = status == "UNFILLED_END_OF_DATA"
    if unfilled:
        return value.get("fill_timestamp") is None and value.get("fill_price") is None and value.get("fee") is None
    return (_is_timestamp(value.get("fill_timestamp")) and _is_decimal(value.get("fill_price"))
            and _is_decimal(value.get("fee")))


def _validate_equity(value: object) -> bool:
    return (type(value) is dict and set(value) == _EQUITY_KEYS and _is_timestamp(value.get("timestamp"))
            and all(_is_decimal(value.get(name)) for name in ("cash", "position", "close", "equity")))


def _validate_result(result: object) -> tuple[dict[str, Any], bytes]:
    """Strictly mirror the SQL receipt schema before crossing the DB boundary."""
    if (type(result) is not dict or set(result) != _RESULT_KEYS
            or result.get("mode") != "OFFLINE_HISTORICAL_ANALYSIS_ONLY"
            or not all(_is_sha256(result.get(field)) for field in ("dataset_sha256", "configuration_sha256", "input_sha256"))):
        _invalid()
    simulation = result["simulation"]
    if (type(simulation) is not dict or set(simulation) != _SIMULATION_KEYS
            or type(simulation.get("symbol")) is not str or _SYMBOL.fullmatch(simulation["symbol"]) is None
            or simulation.get("status") not in _STATUSES or not _is_sha256(simulation.get("provenance"))
            or not all(_is_decimal(simulation.get(name)) for name in ("final_cash", "final_position", "final_equity"))):
        _invalid()
    orders, equity, warnings = simulation.get("orders"), simulation.get("equity"), simulation.get("warnings")
    if (type(orders) is not list or len(orders) > _MAX_ITEMS or not all(_validate_order(item) for item in orders)
            or type(equity) is not list or not 1 <= len(equity) <= _MAX_ITEMS or not all(_validate_equity(item) for item in equity)
            or type(warnings) is not list or warnings not in ([], [_GAP_WARNING])):
        _invalid()
    provenance = result["provenance"]
    if (type(provenance) is not dict or set(provenance) != _PROVENANCE_KEYS
            or not _is_timestamp(provenance.get("as_of")) or provenance.get("status") not in _STATUSES
            or not _is_sha256(provenance.get("engine_provenance_sha256"))):
        _invalid()
    if result["trust_disclaimers"] != list(_TRUST_DISCLAIMERS):
        _invalid()
    document = result["research_document"]
    if document is not None and (type(document) is not dict or set(document) != _DOCUMENT_KEYS
                                 or not _is_sha256(document.get("content_sha256"))
                                 or document.get("untrusted") is not True or document.get("risk_authority") is not False):
        raise ResearchPostgresError("research result contains unsafe document data")
    encoded = _storage_json(result)
    if len(encoded) > _MAX_RESULT_BYTES:
        raise ResearchPostgresError("research result exceeds storage size limit")
    return result, encoded


def _receipt_key(row: object, expected_input_sha256: str) -> str:
    if type(row) is not tuple or len(row) != 1 or type(row[0]) is not str or row[0] != expected_input_sha256:
        raise ResearchPostgresError("database returned an invalid research receipt")
    return row[0]


def _dsn_from_environment() -> str:
    dsn = os.environ.get(_DSN_ENV)
    if type(dsn) is not str or not dsn:
        raise ResearchPostgresError("PostgreSQL recording requires explicit opt-in configuration")
    return dsn


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def run(input_path: str | Path) -> dict[str, Any]:
    """Run offline research then record a bounded, writer-supplied receipt.

    PostgreSQL cannot verify the digest against the original input; it only checks
    digest syntax and equality with the embedded writer-supplied field.  Reusing a
    digest with a changed engine result intentionally conflicts rather than being
    silently accepted.
    """
    result, _encoded = _validate_result(research_cli.run(input_path))
    dsn = _dsn_from_environment()
    connection: Any | None = None
    committed = False
    commit_attempted = False
    try:
        connection = psycopg.connect(dsn, autocommit=False)
        with connection.cursor() as cursor:
            cursor.execute(_SQL, (result["input_sha256"], Jsonb(result)))
            receipt_key = _receipt_key(cursor.fetchone(), result["input_sha256"])
        try:
            commit_attempted = True
            connection.commit()
            committed = True
        except Exception:
            raise ResearchPostgresError("research receipt commit status is unknown; rerun the identical input") from None
    except ResearchPostgresError:
        if connection is not None and not committed and not commit_attempted:
            _rollback_quietly(connection)
        raise
    except Exception:
        if connection is not None and not committed and not commit_attempted:
            _rollback_quietly(connection)
        raise ResearchPostgresError("research receipt was not recorded") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    return {"research_result": result, "receipt": {"key": receipt_key,
            "writer_supplied_input_sha256": result["input_sha256"],
            "digest_verification": "WRITER_SUPPLIED_UNVERIFIED", "recorded": True}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline research and opt in to PostgreSQL receipt recording.")
    parser.add_argument("input", help="local JSON research input (regular file, no symlinks)")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.input), sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (research_cli.ResearchCliError, ResearchPostgresError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
