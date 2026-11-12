import contextlib
import importlib
import io
import json
import os
import time
import unittest
from unittest.mock import Mock, patch
from demo import paper_connection as paper
KEY = "key-NEVER-PRINT"
SECRET = "secret-NEVER-PRINT"
ACCOUNT_ID = "01234567-89ab-cdef-0123-456789abcdef"
OTHER_ID = "11234567-89ab-cdef-0123-456789abcdef"
ENV = {"APCA_API_KEY_ID": KEY, "APCA_API_SECRET_KEY": SECRET}
def payload(**overrides):
    data = {"id": ACCOUNT_ID, "status": "ACTIVE", "account_number": "account-NEVER-PRINT", "cash": "999999"}
    data.update(overrides)
    return json.dumps(data).encode()
class Response:
    def __init__(self, body=None, status=200, length=None):
        self.body = payload() if body is None else body
        self.status = status
        self.length = len(self.body) if length is None else length
        self.read_calls = []
        self.close_calls = 0
    def close(self):
        self.close_calls += 1
    def read(self, n):
        self.read_calls.append(n)
        out = self.body[:n]
        if self.length is not None:
            self.length -= len(out)
        return out


class PaperConnectionTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(paper.http.client, "HTTPSConnection", autospec=True)
        self.connection_type = p.start()
        self.addCleanup(p.stop)
        self.connection = self.connection_type.return_value
        self.response = Response()
        self.connection.getresponse.return_value = self.response

    def test_optional_identity_mismatch_fails_closed(self):
        self.assertIsNone(paper._perform_check(KEY, SECRET, OTHER_ID))
        self.connection.getresponse.return_value = Response()
        self.assertEqual(paper._perform_check(KEY, SECRET, None), ("ACTIVE", False))

    def test_transport_exceptions_are_swallowed_without_details(self):
        for exc in (TimeoutError(SECRET), OSError(KEY), RuntimeError(ACCOUNT_ID)):
            with self.subTest(kind=type(exc)):
                self.connection.getresponse.side_effect = exc
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    self.assertIsNone(paper._perform_check(KEY, SECRET, None))
                self.assertEqual(output.getvalue(), "")
        self.connection.getresponse.side_effect = None
        self.connection.close.side_effect = RuntimeError(SECRET)
        self.assertEqual(paper._perform_check(KEY, SECRET, None), ("ACTIVE", False))

    def test_missing_or_invalid_environment_never_calls_transport(self):
        bad_envs = [{}, {"APCA_API_KEY_ID": KEY}, {"APCA_API_KEY_ID": "", "APCA_API_SECRET_KEY": SECRET},
                    {**ENV, "APCA_API_KEY_ID": "bad\r\nInjected: x"},
                    {**ENV, "APCA_API_SECRET_KEY": "a" * 257},
                    {**ENV, "APCA_EXPECTED_ACCOUNT_ID": ""},
                    {**ENV, "APCA_EXPECTED_ACCOUNT_ID": "https://evil.invalid"}]
        for env in bad_envs:
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True), \
                 patch.object(paper, "_run_bounded") as run:
                result = paper.check_paper_connection()
                self.assertFalse(result.connected)
                run.assert_not_called()
        self.connection_type.assert_not_called()

    def test_result_and_cli_print_only_safe_facts(self):
        with patch.dict(os.environ, {**ENV, "APCA_EXPECTED_ACCOUNT_ID": ACCOUNT_ID}, clear=True), \
             patch.object(paper, "_run_bounded", return_value=("ACTIVE", True)) as run:
            result = paper.check_paper_connection()
            self.assertTrue(result.connected)
            self.assertEqual(result.account_status, "ACTIVE")
            self.assertTrue(result.identity_verified)
            self.assertRegex(result.checked_at, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(paper.main([]), 0)
            text = output.getvalue() + repr(result)
            for hidden in (KEY, SECRET, ACCOUNT_ID, "account-NEVER-PRINT", "999999"):
                self.assertNotIn(hidden, text)
            self.assertIn("Account status: ACTIVE", text)
            self.assertIn("identity: verified", text)
            self.assertIn("independent of the simulator", text)
            run.assert_called_with(KEY, SECRET, ACCOUNT_ID)
        with patch.dict(os.environ, ENV, clear=True), patch.object(paper, "_run_bounded", return_value=("ACTIVE", False)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(paper.main([]), 0)
            self.assertIn("not configured; not verified", output.getvalue())

    def test_failures_and_command_line_host_injection_do_not_leak(self):
        with patch.dict(os.environ, ENV, clear=True), \
             patch.object(paper, "_run_bounded", side_effect=RuntimeError(SECRET)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(paper.main([]), 1)
            self.assertIn("not verified", output.getvalue())
            for hidden in (SECRET, KEY, ACCOUNT_ID):
                self.assertNotIn(hidden, output.getvalue())
        with patch.object(paper, "check_paper_connection") as check:
            for args in (["--url", "https://evil.invalid"], ["--key", KEY], ["https://evil.invalid"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    self.assertEqual(paper.main(args), 2)
                for arg in args:
                    self.assertNotIn(arg, output.getvalue())
            check.assert_not_called()
        with self.assertRaises(TypeError):
            paper.check_paper_connection(url="https://evil.invalid")
        self.connection_type.assert_not_called()


if __name__ == "__main__":
    unittest.main()
