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

    def test_configuration_is_fixed_and_help_explains_limits(self):
        self.assertEqual((private.HOST, private.PORT), ("127.0.0.1", 8765))
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("127.0.0.1:8765:127.0.0.1:8765", result.stdout)
        self.assertIn("not a deployment", result.stdout)
        self.assertIn("fixture quotes", result.stdout)
        self.assertIn("other users/processes", result.stdout)
        self.assertNotIn("traceback", result.stderr.lower())

    def test_bad_arguments_do_not_echo_sensitive_input(self):
        secret = "sensitive-value-not-to-log"
        for args in [("--host", secret), ("--serve", "--session-dir", "relative/" + secret),
                     ("--serve", "--session-dir", str(self.directory), "--port", secret)]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(secret, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.token_file.exists())

    def test_directory_must_be_private_and_not_symlink(self):
        os.chmod(self.directory, 0o755)
        result = self.run_cli("--check", "--session-dir", str(self.directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("0700", result.stderr)
        os.chmod(self.directory, 0o700)
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.directory, target_is_directory=True)
        result = self.run_cli("--check", "--session-dir", str(link))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.token_file.exists())

    def test_symlink_in_ancestor_and_dotdot_are_rejected(self):
        link = Path(self.temp.name) / "ancestor"
        link.symlink_to(self.directory, target_is_directory=True)
        child = self.directory / "child"
        child.mkdir(mode=0o700)
        for path in (str(link / "child"), str(link) + "/", str(child / "..")):
            with self.subTest(path=path):
                self.assertNotEqual(self.run_cli("--check", "--session-dir", path).returncode, 0)

    def test_directory_permissions_rechecked_before_creation(self):
        fd = private.private_directory(str(self.directory))
        self.addCleanup(os.close, fd)
        os.chmod(self.directory, 0o755)
        with self.assertRaises(private.SafeFailure):
            private.write_token(fd, "not-logged")
        self.assertFalse(self.token_file.exists())

    def test_failed_write_cleans_up_and_partial_writes_finish(self):
        fd = private.private_directory(str(self.directory))
        self.addCleanup(os.close, fd)
        with mock.patch.object(private.os, "fsync", side_effect=OSError("secret")):
            with self.assertRaises(OSError):
                private.write_token(fd, "not-logged")
        self.assertFalse(self.token_file.exists())
        original_write = os.write
        with mock.patch.object(private.os, "write", side_effect=lambda f, b: original_write(f, b[:2])):
            token_fd = private.write_token(fd, "partial-write")
        self.addCleanup(os.close, token_fd)
        self.assertEqual(self.token_file.read_text(), "partial-write\n")
        private.remove_token(fd, token_fd)
        self.assertFalse(self.token_file.exists())

    def test_symlink_replacement_is_not_removed(self):
        fd = private.private_directory(str(self.directory))
        self.addCleanup(os.close, fd)
        token_fd = private.write_token(fd, "token")
        self.addCleanup(os.close, token_fd)
        self.token_file.unlink()
        victim = Path(self.temp.name) / "victim"
        victim.write_text("safe")
        self.token_file.symlink_to(victim)
        private.remove_token(fd, token_fd)
        self.assertTrue(self.token_file.is_symlink())
        self.assertEqual(victim.read_text(), "safe")

    def test_wrong_owner_is_rejected(self):
        real_fstat = os.fstat
        def fake_fstat(fd):
            info = list(real_fstat(fd))
            info[4] = os.geteuid() + 1
            return os.stat_result(info)
        with mock.patch.object(private.os, "fstat", side_effect=fake_fstat):
            with self.assertRaises(private.SafeFailure):
                private.private_directory(str(self.directory))

    def test_existing_file_and_symlink_fail_closed_without_overwrite(self):
        self.token_file.write_text("keep-me")
        for action in ("--check", "--serve"):
            result = self.run_cli(action, "--session-dir", str(self.directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.token_file.read_text(), "keep-me")
            self.assertNotIn("keep-me", result.stdout + result.stderr)
        self.token_file.unlink()
        victim = Path(self.temp.name) / "victim"
        victim.write_text("unchanged")
        self.token_file.symlink_to(victim)
        result = self.run_cli("--serve", "--session-dir", str(self.directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(victim.read_text(), "unchanged")

    def test_exclusive_create_and_replacement_safe_cleanup(self):
        fd = private.private_directory(str(self.directory))
        self.addCleanup(os.close, fd)
        identity = private.write_token(fd, "test-token")
        self.addCleanup(os.close, identity)
        self.assertEqual(stat.S_IMODE(self.token_file.stat().st_mode), 0o600)
        with self.assertRaises(private.SafeFailure):
            private.write_token(fd, "new-token")
        self.assertEqual(self.token_file.read_text(), "test-token\n")
        self.token_file.rename(self.directory / "old")
        self.token_file.write_text("replacement")
        private.remove_token(fd, identity)
        self.assertEqual(self.token_file.read_text(), "replacement")


if __name__ == "__main__":
    unittest.main()
