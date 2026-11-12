"""Unit tests for the explicit PostgreSQL research receipt connector."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import subprocess
import sys
import traceback
import unittest
from unittest.mock import MagicMock, patch

import psycopg

from app import research_postgres


ROOT = Path(__file__).parents[1]
DSN_ENV = "ASAI_RESEARCH_POSTGRES_DSN"
DIGEST = "a" * 64


def result(document=None):
    return {
        "mode": "OFFLINE_HISTORICAL_ANALYSIS_ONLY",
        "simulation": {
            "symbol": "TEST", "orders": [],
            "equity": [{"timestamp": "2026-01-01T00:00:00+00:00", "cash": "100", "position": "0", "close": "1", "equity": "100"}],
            "final_cash": "100", "final_position": "0", "final_equity": "100", "provenance": DIGEST,
            "status": "COMPLETED", "warnings": [],
        },
        "provenance": {"as_of": "2026-01-01T00:00:00+00:00", "status": "COMPLETED", "engine_provenance_sha256": DIGEST},
        "dataset_sha256": DIGEST, "configuration_sha256": DIGEST, "input_sha256": DIGEST,
        "research_document": document,
        "trust_disclaimers": list(research_postgres._TRUST_DISCLAIMERS),
    }


class ResearchPostgresTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {DSN_ENV: "postgresql://safe@db/research"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.cursor.fetchone.return_value = (DIGEST,)

    def test_accepted_result_runs_cli_first_and_records_parameterized_json(self):
        with patch.object(research_postgres.research_cli, "run", return_value=result()) as cli, patch.object(research_postgres.psycopg, "connect", return_value=self.connection) as connect:
            response = research_postgres.run("input.json")

        cli.assert_called_once_with("input.json")
        connect.assert_called_once_with("postgresql://safe@db/research", autocommit=False)
        self.cursor.execute.assert_called_once()
        sql, parameters = self.cursor.execute.call_args.args
        self.assertEqual("SELECT asai.record_research_run(%s, %s::jsonb)", sql)
        self.assertEqual(DIGEST, parameters[0])
        self.assertIsInstance(parameters[1], research_postgres.Jsonb)
        self.assertEqual(result(), parameters[1].obj)
        self.connection.commit.assert_called_once_with()
        self.connection.rollback.assert_not_called()
        self.connection.close.assert_called_once_with()
        self.assertEqual(DIGEST, response["receipt"]["key"])
        self.assertEqual(DIGEST, response["receipt"]["writer_supplied_input_sha256"])
        self.assertEqual("WRITER_SUPPLIED_UNVERIFIED", response["receipt"]["digest_verification"])
        self.assertNotIn("input_sha256", response["receipt"])
        self.assertEqual(result(), response["research_result"])

    def test_invalid_result_is_not_connected_or_stored(self):
        unsafe = result({"text": "plaintext must never be stored"})
        with patch.object(research_postgres.research_cli, "run", return_value=unsafe), patch.object(research_postgres.psycopg, "connect") as connect:
            with self.assertRaisesRegex(research_postgres.ResearchPostgresError, "unsafe document"):
                research_postgres.run("input.json")
        connect.assert_not_called()

    def test_null_and_wrong_json_types_are_not_connected_or_stored(self):
        for field, value in (("dataset_sha256", None), ("mode", True), ("trust_disclaimers", [])):
            unsafe = result()
            unsafe[field] = value
            with self.subTest(field=field), patch.object(research_postgres.research_cli, "run", return_value=unsafe), patch.object(research_postgres.psycopg, "connect") as connect:
                with self.assertRaisesRegex(research_postgres.ResearchPostgresError, "research result is invalid"):
                    research_postgres.run("input.json")
            connect.assert_not_called()

    def test_no_fallback_without_explicit_postgres_opt_in(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(research_postgres.research_cli, "run", return_value=result()), patch.object(research_postgres.psycopg, "connect") as connect:
            with self.assertRaisesRegex(research_postgres.ResearchPostgresError, "explicit opt-in"):
                research_postgres.run("input.json")
        connect.assert_not_called()

    def test_execution_failure_rolls_back_and_returns_safe_error(self):
        self.cursor.execute.side_effect = psycopg.OperationalError("password=top-secret")
        with patch.object(research_postgres.research_cli, "run", return_value=result()), patch.object(research_postgres.psycopg, "connect", return_value=self.connection):
            with self.assertRaisesRegex(research_postgres.ResearchPostgresError, "not recorded") as caught:
                research_postgres.run("input.json")
        self.assertNotIn("top-secret", str(caught.exception))
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_not_called()
        self.connection.close.assert_called_once_with()

    def test_non_driver_connection_error_is_sanitized_and_never_leaks_dsn(self):
        secret = "postgresql://alice:do-not-print@db/research"
        with patch.dict(os.environ, {DSN_ENV: secret}, clear=True), patch.object(research_postgres.research_cli, "run", return_value=result()), patch.object(research_postgres.psycopg, "connect", side_effect=ValueError(secret)):
            with self.assertRaisesRegex(research_postgres.ResearchPostgresError, "not recorded") as caught:
                research_postgres.run("input.json")
        self.assertNotIn(secret, str(caught.exception))

    def test_mismatched_database_receipt_rolls_back_and_is_not_acknowledged(self):
        self.cursor.fetchone.return_value = ("b" * 64,)
        with patch.object(research_postgres.research_cli, "run", return_value=result()), patch.object(research_postgres.psycopg, "connect", return_value=self.connection):
            with self.assertRaisesRegex(research_postgres.ResearchPostgresError, "invalid research receipt"):
                research_postgres.run("input.json")
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_not_called()

    def test_ambiguous_commit_fails_closed_without_rollback_or_reconnect(self):
        self.connection.commit.side_effect = ValueError("connection lost")
        with patch.object(research_postgres.research_cli, "run", return_value=result()), patch.object(research_postgres.psycopg, "connect", return_value=self.connection) as connect:
            with self.assertRaisesRegex(research_postgres.ResearchPostgresError, "rerun the identical input"):
                research_postgres.run("input.json")
        connect.assert_called_once()
        self.connection.rollback.assert_not_called()
        self.connection.close.assert_called_once_with()

    def test_cli_error_never_leaks_connection_credentials(self):
        secret = "postgresql://alice:do-not-print@db/research"
        with patch.dict(os.environ, {DSN_ENV: secret}, clear=True), patch.object(research_postgres.research_cli, "run", return_value=result()), patch.object(research_postgres.psycopg, "connect", side_effect=psycopg.OperationalError(secret)):
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as exited:
                with patch.object(sys, "argv", ["research_postgres", "input.json"]):
                    research_postgres.main()
        self.assertEqual(2, exited.exception.code)
        self.assertNotIn(secret, stderr.getvalue())
        self.assertIn("research receipt was not recorded", stderr.getvalue())

    def test_broker_is_never_imported_or_touched(self):
        self.assertNotIn("broker", research_postgres.__dict__)
        with patch.dict(sys.modules, {"broker": None}), patch.object(research_postgres.research_cli, "run", return_value=result()), patch.object(research_postgres.psycopg, "connect", return_value=self.connection):
            research_postgres.run("input.json")
        self.assertNotIn("broker", research_postgres.__dict__)

    def test_cli_has_no_missing_driver_fallback(self):
        invoked = subprocess.run(
            [sys.executable, "-S", "-m", "app.research_postgres", "input.json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env={"PATH": os.environ.get("PATH", "")},
            check=False,
        )
        self.assertNotEqual(0, invoked.returncode)
        self.assertIn("psycopg", invoked.stderr)


if __name__ == "__main__":
    unittest.main()
