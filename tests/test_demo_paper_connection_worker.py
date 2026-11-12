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

    def test_worker_deadline_and_private_ipc(self):
        exc = paper.subprocess.TimeoutExpired("safe", 10, output=SECRET)
        with patch.object(paper.subprocess, "run", side_effect=exc) as run:
            self.assertIsNone(paper._run_bounded(KEY, SECRET, ACCOUNT_ID))
        args, kwargs = run.call_args
        self.assertEqual(kwargs["timeout"], 10.0)
        self.assertEqual(kwargs["stderr"], paper.subprocess.DEVNULL)
        self.assertEqual(kwargs["env"], {})
        self.assertEqual(json.loads(kwargs["input"]), [KEY, SECRET, ACCOUNT_ID])
        for secret in (KEY, SECRET, ACCOUNT_ID):
            self.assertNotIn(secret, repr(args))

    def test_deadline_terminates_a_stalled_local_worker_without_output(self):
        real_run = paper.subprocess.run
        def stalled_worker(_command, **kwargs):
            script = ('import sys,time; data=sys.stdin.buffer.read(); '
                      'sys.stdout.buffer.write(data); sys.stdout.buffer.flush(); time.sleep(30)')
            return real_run([paper.sys.executable, '-I', '-S', '-c', script], **kwargs)
        output = io.StringIO()
        start = time.monotonic()
        with patch.object(paper, '_DEADLINE', 0.2), \
             patch.object(paper.subprocess, 'run', side_effect=stalled_worker), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertIsNone(paper._run_bounded(KEY, SECRET, ACCOUNT_ID))
        self.assertLess(time.monotonic() - start, 5.0)
        self.assertEqual(output.getvalue(), '')

    def test_worker_result_allowlist_and_identity_validation(self):
        for worker_result, expected, good in [(["ACTIVE", True], ACCOUNT_ID, True),
                                               (["ACTIVE", False], None, True),
                                               (["ACTIVE", True], None, False),
                                               (["EVIL-SECRET", False], None, False),
                                               (["ACTIVE", 1], ACCOUNT_ID, False),
                                               (None, None, False)]:
            with self.subTest(worker_result=worker_result):
                completed = Mock(returncode=0, stdout=json.dumps(worker_result).encode())
                with patch.object(paper.subprocess, "run", return_value=completed):
                    result = paper._run_bounded(KEY, SECRET, expected)
                self.assertEqual(result, tuple(worker_result) if good else None)
        for completed in (Mock(returncode=1, stdout=b'[]'), Mock(returncode=0, stdout=b'x' * 257)):
            with patch.object(paper.subprocess, "run", return_value=completed):
                self.assertIsNone(paper._run_bounded(KEY, SECRET, None))

    def test_isolated_python_worker_runs_with_mocked_transport(self):
        script = ("import runpy,sys; n=runpy.run_path(sys.argv[1]); "
                  "n['_subprocess_main'].__globals__['_perform_check']="
                  "lambda key,secret,expected: ('ACTIVE', expected is not None); "
                  "n['_subprocess_main']()")
        completed = paper.subprocess.run(
            [paper.sys.executable, '-I', '-S', '-c', script, paper.__file__],
            input=json.dumps([KEY, SECRET, ACCOUNT_ID]).encode(),
            stdout=paper.subprocess.PIPE, stderr=paper.subprocess.PIPE, env={}, timeout=10)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, b'')
        self.assertEqual(json.loads(completed.stdout), ['ACTIVE', True])
        for value in (KEY, SECRET, ACCOUNT_ID):
            self.assertNotIn(value.encode(), completed.stdout + completed.stderr)

    def test_worker_never_sends_raw_exception(self):
        source = io.TextIOWrapper(io.BytesIO(json.dumps([KEY, SECRET, None]).encode()))
        output = io.StringIO()
        with patch.object(paper.sys, "stdin", source), \
             patch.object(paper, "_perform_check", side_effect=RuntimeError(SECRET)), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            paper._subprocess_main()
        self.assertEqual(output.getvalue(), "")

    def test_worker_success_returns_only_status_and_identity(self):
        source = io.TextIOWrapper(io.BytesIO(json.dumps([KEY, SECRET, ACCOUNT_ID]).encode()))
        output = io.StringIO()
        with patch.object(paper.sys, "stdin", source), \
             patch.object(paper, "_perform_check", return_value=("ACTIVE", True)), \
             contextlib.redirect_stdout(output):
            paper._subprocess_main()
        self.assertEqual(json.loads(output.getvalue()), ["ACTIVE", True])
        for value in (KEY, SECRET, ACCOUNT_ID):
            self.assertNotIn(value, output.getvalue())


if __name__ == "__main__":
    unittest.main()
