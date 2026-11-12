"""Offline/local tests for the optional private simulator deployment aid."""
from __future__ import annotations
import contextlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "demo_private_deploy.py"
spec = importlib.util.spec_from_file_location("demo_private_deploy", SCRIPT)
assert spec and spec.loader
private = importlib.util.module_from_spec(spec)
spec.loader.exec_module(private)


class PrivateDeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "private"
        self.directory.mkdir(mode=0o700)
        self.token_file = self.directory / private.TOKEN_NAME

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              cwd=self.temp.name, timeout=10, check=False)

    def test_server_close_failure_cannot_prevent_token_cleanup(self):
        import demo.server
        fd = private.private_directory(str(self.directory))
        self.addCleanup(os.close, fd)
        server = mock.Mock(server_address=(private.HOST, private.PORT), session_token="sensitive-token")
        server.serve_forever.side_effect = KeyboardInterrupt
        server.server_close.side_effect = OSError("close failed")
        with mock.patch.object(demo.server, "make_server", return_value=server):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(OSError):
                    private.serve(fd)
        self.assertFalse(self.token_file.exists())
        server.server_close.assert_called_once()

    def test_sigterm_during_token_publication_cleans_up(self):
        bootstrap = ("import importlib.util,os,signal,sys; "
                     "s=importlib.util.spec_from_file_location('private_test',sys.argv[1]); "
                     "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                     "orig=m.write_token; "
                     "exec('def interrupted(fd, token):\\n result=orig(fd, token)\\n os.kill(os.getpid(), signal.SIGTERM)\\n return result'); "
                     "m.write_token=interrupted; sys.exit(m.main(sys.argv[2:]))")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        bootstrap = bootstrap.replace("orig=m.write_token;", f"m.PORT={port}; orig=m.write_token;")
        result = subprocess.run([sys.executable, "-c", bootstrap, str(SCRIPT), "--serve", "--session-dir", str(self.directory)],
                                cwd=self.temp.name, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.token_file.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_unavailable_port_fails_check_and_serve(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            with mock.patch.object(private, "PORT", sock.getsockname()[1]):
                for action in ("--check", "--serve"):
                    output, errors = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                        result = private.main([action, "--session-dir", str(self.directory)])
                    self.assertEqual(result, 1)
                    self.assertIn("loopback port 8765", errors.getvalue())
                    self.assertFalse(self.token_file.exists())

    def test_preflight_and_simulator_integration_no_secret_logs(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        bootstrap = ("import importlib.util,sys,socket; "
                     "socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('outbound blocked')); "
                     "socket.socket.connect_ex=socket.socket.connect; "
                     "socket.create_connection=socket.socket.connect; "
                     "s=importlib.util.spec_from_file_location('private_test',sys.argv[1]); "
                     "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                     "m.PORT=int(sys.argv[2]); sys.exit(m.main(sys.argv[3:]))")
        prefix = [sys.executable, "-c", bootstrap, str(SCRIPT), str(port)]
        check = subprocess.run(prefix + ["--check", "--session-dir", str(self.directory)],
                               cwd=self.temp.name, text=True, capture_output=True, timeout=10)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("no deployment performed", check.stdout)
        self.assertFalse(self.token_file.exists())
        env = os.environ.copy()
        env.update(APCA_API_KEY_ID="fake-key-for-log-test", APCA_API_SECRET_KEY="fake-secret-for-log-test")
        process = subprocess.Popen(prefix + ["--serve", "--session-dir", str(self.directory)],
                                   cwd=self.temp.name, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = stderr = ""
        token = ""
        try:
            deadline = time.monotonic() + 5
            while not self.token_file.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(self.token_file.exists(), "token file not created")
            self.assertEqual(stat.S_IMODE(self.token_file.stat().st_mode), 0o600)
            while not token and process.poll() is None and time.monotonic() < deadline:
                token = self.token_file.read_text().strip()
                if not token:
                    time.sleep(0.02)
            self.assertGreaterEqual(len(token), 32)
            conn = http.client.HTTPConnection(private.HOST, port, timeout=3)
            self.addCleanup(conn.close)
            conn.request("GET", "/")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            page = response.read().decode()
            self.assertNotIn(token, page)
            self.assertNotIn("console.log", page)
            self.assertIn("session token from the private token file", page)
            self.assertNotIn("session token printed by the local server", page)
            conn.request("GET", "/secret/" + token, headers={"X-Session-Token": token})
            response = conn.getresponse()
            self.assertEqual(response.status, 404)
            self.assertNotIn(token, response.read().decode())
            conn.request("GET", "/health")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["service"], "local_simulator")
            conn.request("GET", "/api/quote?symbol=AAPL", headers={"X-Session-Token": token})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["quote"]["source"], "fixture")
            conn.request("GET", "/api/quote?symbol=AAPL", headers={"X-Session-Token": "wrong"})
            response = conn.getresponse()
            self.assertEqual(response.status, 401)
            response.read()
            conn.request("GET", "/health", headers={"Host": "example.com"})
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            payload = json.dumps({"probe": "body"})
            conn.request("POST", "/api/orders", body=payload,
                         headers={"X-Session-Token": token, "Content-Type": "application/json"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            self.assertEqual(response.getheader("Connection"), "close")
            response.read()
            conn.request("GET", "/health")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            conn.request(token, "/")
            response = conn.getresponse()
            self.assertEqual(response.status, 501)
            self.assertNotIn(token, response.read().decode())
            self.assertEqual(self.run_cli("--check", "--session-dir", str(self.directory)).returncode, 1)
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
                self.fail("private simulator did not stop on SIGTERM")
        self.assertEqual(process.returncode, 0, stderr)
        self.assertFalse(self.token_file.exists())
        self.assertNotIn(token, stdout + stderr)
        self.assertNotIn("fake-key-for-log-test", stdout + stderr)
        self.assertNotIn("fake-secret-for-log-test", stdout + stderr)
        self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main()
