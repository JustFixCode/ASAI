"""Genuine PostgreSQL integration checks for the opt-in research recorder."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

ADMIN_DSN_ENV = "ASAI_RESEARCH_TEST_DATABASE_URL"
WRITER_DSN_ENV = "ASAI_RESEARCH_POSTGRES_DSN"

# Keep normal unittest discovery dependency-free. This module is an opt-in
# integration suite, so importing it without either DSN must not require the
# optional PostgreSQL adapter or the recorder module (which imports it too).
try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError as exc:
    psycopg = None
    Jsonb = None
    _PSYCOPG_IMPORT_ERROR: ImportError | None = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

_ADMIN_DSN = os.environ.get(ADMIN_DSN_ENV)
_WRITER_DSN = os.environ.get(WRITER_DSN_ENV)
_ADMIN_DSN_SET = ADMIN_DSN_ENV in os.environ
_WRITER_DSN_SET = WRITER_DSN_ENV in os.environ

if _ADMIN_DSN_SET != _WRITER_DSN_SET:
    raise RuntimeError(
        f"{ADMIN_DSN_ENV} and {WRITER_DSN_ENV} must be set together for PostgreSQL integration tests"
    )
if _ADMIN_DSN_SET and (not _ADMIN_DSN or not _WRITER_DSN):
    raise RuntimeError("PostgreSQL integration-test DSNs must be non-empty when explicitly set")

_INTEGRATION_ENABLED = _ADMIN_DSN_SET and _WRITER_DSN_SET
if _INTEGRATION_ENABLED and psycopg is None:
    raise RuntimeError(
        "PostgreSQL integration tests were explicitly enabled but psycopg is not installed"
    ) from _PSYCOPG_IMPORT_ERROR

if _INTEGRATION_ENABLED:
    from app import research_postgres
else:
    research_postgres = None


def valid_fixture() -> dict[str, object]:
    """A valid, caller-supplied offline fixture; it has no network or order data."""
    return {
        "schema_version": 1,
        "as_of": "2026-01-02T14:35:00+00:00",
        "bars": [
            {"open_timestamp": "2026-01-02T14:30:00+00:00", "close_timestamp": "2026-01-02T14:30:59+00:00", "symbol": "ASAI", "open": "10", "close": "10"},
            {"open_timestamp": "2026-01-02T14:31:00+00:00", "close_timestamp": "2026-01-02T14:31:59+00:00", "symbol": "ASAI", "open": "9", "close": "9"},
            {"open_timestamp": "2026-01-02T14:32:00+00:00", "close_timestamp": "2026-01-02T14:32:59+00:00", "symbol": "ASAI", "open": "8", "close": "8"},
            {"open_timestamp": "2026-01-02T14:33:00+00:00", "close_timestamp": "2026-01-02T14:33:59+00:00", "symbol": "ASAI", "open": "12", "close": "12"},
            {"open_timestamp": "2026-01-02T14:34:00+00:00", "close_timestamp": "2026-01-02T14:34:59+00:00", "symbol": "ASAI", "open": "13", "close": "3"},
        ],
        "strategy": {"type": "sma_crossover", "short_window": 2, "long_window": 3},
        "config": {"initial_cash": "1000", "order_quantity": "1", "max_position": "1", "max_gap_seconds": 60, "fee_bps": "0", "slippage_bps": "0"},
    }


@unittest.skipUnless(
    _INTEGRATION_ENABLED,
    f"set both {ADMIN_DSN_ENV} and {WRITER_DSN_ENV} to run PostgreSQL integration tests",
)
class ResearchPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.admin_dsn = _ADMIN_DSN
        self.writer_dsn = _WRITER_DSN
        self.tmp = tempfile.TemporaryDirectory()
        self.input_path = Path(self.tmp.name) / "research.json"
        self.input_path.write_text(json.dumps(valid_fixture()), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _admin_scalar(self, sql: str, parameters: tuple[object, ...]) -> object:
        with psycopg.connect(self.admin_dsn) as connection, connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cursor.fetchone()[0]

    def _admin_row(self, sql: str, parameters: tuple[object, ...]) -> tuple[object, ...]:
        with psycopg.connect(self.admin_dsn) as connection, connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            row = cursor.fetchone()
        self.assertIsNotNone(row)
        return row

    def test_login_principal_inherits_only_the_nologin_writer_capability(self) -> None:
        with psycopg.connect(self.writer_dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, session_user, "
                "pg_has_role(session_user, 'asai_research_writer', 'MEMBER'), "
                "has_schema_privilege(current_user, 'asai', 'USAGE')"
            )
            current_user, session_user, is_writer_member, has_schema_usage = cursor.fetchone()

        self.assertEqual("asai_research_test", current_user)
        self.assertEqual("asai_research_test", session_user)
        self.assertTrue(is_writer_member)
        self.assertTrue(has_schema_usage)
        self.assertEqual(
            (False, False, False, False, False, False, False),
            self._admin_row(
                "SELECT rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolcreatedb, "
                "rolreplication, rolbypassrls FROM pg_roles "
                "WHERE rolname = 'asai_research_writer'",
                (),
            ),
        )
        self.assertEqual(
            (True, True, False, False, False, False, False),
            self._admin_row(
                "SELECT rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolcreatedb, "
                "rolreplication, rolbypassrls FROM pg_roles "
                "WHERE rolname = 'asai_research_test'",
                (),
            ),
        )

    def test_runner_records_valid_fixture_idempotently_with_constrained_role(self) -> None:
        first = research_postgres.run(self.input_path)
        second = research_postgres.run(self.input_path)
        self.assertEqual(first, second)
        digest = first["receipt"]["writer_supplied_input_sha256"]
        self.assertEqual(digest, first["receipt"]["key"])
        self.assertEqual(1, self._admin_scalar("SELECT count(*) FROM asai.research_run WHERE input_sha256 = %s", (digest,)))
        self.assertEqual(digest, self._admin_scalar("SELECT result->>'input_sha256' FROM asai.research_run WHERE input_sha256 = %s", (digest,)))
        self.assertEqual("asai_research_test", self._admin_scalar(
            "SELECT recorded_by::text FROM asai.research_run WHERE input_sha256 = %s", (digest,)
        ))

        conflicting = copy.deepcopy(first["research_result"])
        conflicting["simulation"]["status"] = "CONFLICT"
        with psycopg.connect(self.writer_dsn) as connection, connection.cursor() as cursor:
            with self.assertRaises(psycopg.Error):
                cursor.execute("SELECT asai.record_research_run(%s, %s::jsonb)", (digest, Jsonb(conflicting)))
            connection.rollback()

        with psycopg.connect(self.writer_dsn) as connection, connection.cursor() as cursor:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                cursor.execute("SELECT * FROM asai.research_run")
            connection.rollback()

    def test_function_participates_in_real_transaction_rollback(self) -> None:
        result = research_postgres.research_cli.run(self.input_path)
        rollback_digest = "f" * 64
        result["input_sha256"] = rollback_digest
        with psycopg.connect(self.writer_dsn, autocommit=False) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT asai.record_research_run(%s, %s::jsonb)", (rollback_digest, Jsonb(result)))
            connection.rollback()
        self.assertEqual(0, self._admin_scalar("SELECT count(*) FROM asai.research_run WHERE input_sha256 = %s", (rollback_digest,)))


if __name__ == "__main__":
    unittest.main()
