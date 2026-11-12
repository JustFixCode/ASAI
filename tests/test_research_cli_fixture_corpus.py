"""Security and regression corpus for bounded offline research input validation."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from app.research_cli import ResearchCliError, run


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "research_cli_security_regression"
EXPECTED_COUNT = 200


class ResearchCliFixtureCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = sorted(FIXTURE_DIR.glob("*.json"))
        if len(cls.paths) != EXPECTED_COUNT:
            raise AssertionError(f"fixture corpus must contain exactly {EXPECTED_COUNT} files")

        cls.fixtures: list[tuple[Path, dict[str, object], bytes]] = []
        seen_cases: set[str] = set()
        seen_payloads: set[bytes] = set()
        for number, fixture_path in enumerate(cls.paths, start=1):
            if not fixture_path.name.startswith(f"{number:03d}_"):
                raise AssertionError("fixture files must have contiguous three-digit sequence prefixes")
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            expected_keys = ({"case", "category", "note", "expected", "input"}
                             if "input" in fixture else {"case", "category", "note", "expected", "raw_input"})
            if set(fixture) != expected_keys:
                raise AssertionError(f"{fixture_path.name} has an invalid fixture schema")
            case = fixture["case"]
            if type(case) is not str or not case or case in seen_cases:
                raise AssertionError(f"{fixture_path.name} has a missing or duplicate case ID")
            seen_cases.add(case)
            expected = fixture["expected"]
            if type(expected) is not dict or expected.get("outcome") not in {"success", "error"}:
                raise AssertionError(f"{fixture_path.name} has an invalid expected outcome")
            if set(expected) != ({"outcome", "mode"} if expected["outcome"] == "success" else {"outcome"}):
                raise AssertionError(f"{fixture_path.name} has an invalid expected result schema")
            if expected.get("mode") not in {None, "OFFLINE_HISTORICAL_ANALYSIS_ONLY"}:
                raise AssertionError(f"{fixture_path.name} has an unsupported expected mode")
            raw = (json.dumps(fixture["input"], separators=(",", ":"), ensure_ascii=True)
                   if "input" in fixture else fixture["raw_input"])
            if type(raw) is not str:
                raise AssertionError(f"{fixture_path.name} raw input must be text")
            payload = raw.encode("utf-8", "surrogatepass")
            if payload in seen_payloads:
                raise AssertionError(f"{fixture_path.name} duplicates an actual input payload")
            seen_payloads.add(payload)
            cls.fixtures.append((fixture_path, fixture, payload))

        if len(seen_cases) != EXPECTED_COUNT or len(seen_payloads) != EXPECTED_COUNT:
            raise AssertionError("fixture corpus IDs and actual input payloads must each be unique")

    def test_all_cases_invoke_real_offline_research_without_network_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            for fixture_path, fixture, payload in self.fixtures:
                expected = fixture["expected"]
                with self.subTest(case=fixture["case"], category=fixture["category"]):
                    input_path.write_bytes(payload)
                    before = input_path.read_bytes()
                    directory_before = sorted(path.name for path in input_path.parent.iterdir())
                    with patch.object(socket, "create_connection", side_effect=AssertionError("network is forbidden")) as connection, \
                         patch.object(socket.socket, "connect", side_effect=AssertionError("network is forbidden")) as socket_connect:
                        if expected["outcome"] == "success":
                            result = run(input_path)
                            self.assertEqual(expected["mode"], result["mode"])
                            self.assertEqual("OFFLINE_HISTORICAL_ANALYSIS_ONLY", result["mode"])
                            self.assertIn("No network, credentials, broker, trading, order submission, control, risk, or manifest override path is used; simulated orders are not real orders.", result["trust_disclaimers"])
                        else:
                            with self.assertRaises(ResearchCliError):
                                run(input_path)
                    connection.assert_not_called()
                    socket_connect.assert_not_called()
                    self.assertEqual(before, input_path.read_bytes(), "analysis must not mutate caller input")
                    self.assertEqual(directory_before, sorted(path.name for path in input_path.parent.iterdir()),
                                     "analysis must not create files beside caller input")


if __name__ == "__main__":
    unittest.main()
