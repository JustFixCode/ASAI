import fcntl
import json
import os
import socket
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.manifest import MAX_MANIFEST_BYTES, ConfigurationError, load_manifest, manifest_digest, normalize_manifest
from memory.audit_store import AuditStore, MemoryError


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "asai_safe.yaml"


class YamlManifestSafetyTests(unittest.TestCase):
    def write_manifest(self, directory, payload):
        path = Path(directory) / "candidate.yaml"
        path.write_text(payload, encoding="utf-8")
        return path

    def test_accepts_the_disabled_json_compatible_yaml_manifest(self):
        config = load_manifest(MANIFEST_PATH)
        self.assertEqual(config["market_data"]["provider"], "unconfigured")
        self.assertFalse(config["market_data"]["retrieval_enabled"])
        self.assertFalse(config["market_data"]["live_data_enabled"])
        self.assertFalse(config["market_data"]["network_enabled"])
        self.assertEqual(config["broker"]["provider"], "alpaca")
        self.assertEqual(config["broker"]["mode"], "paper")
        self.assertFalse(config["broker"]["live_trading_enabled"])
        self.assertFalse(config["broker"]["execution_enabled"])
        self.assertFalse(config["broker"]["submission_enabled"])
        self.assertEqual(config["memory"]["purpose"], "configuration_audit_history")
        self.assertFalse(config["memory"]["autonomous_updates_enabled"])
        self.assertTrue(config["memory"]["human_review_required"])

    def test_malformed_and_duplicate_documents_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for payload in (
                "market_data: disabled\n",  # YAML syntax deliberately unsupported.
                '{"schema_version": 1, "schema_version": 1}',
                "",
            ):
                with self.subTest(payload=payload):
                    with self.assertRaises(ConfigurationError):
                        load_manifest(self.write_manifest(directory, payload))

    def test_all_live_or_execute_enable_modes_are_denied(self):
        baseline = load_manifest(MANIFEST_PATH)
        rejected = (
            ("market_data", "retrieval_enabled"),
            ("market_data", "live_data_enabled"),
            ("market_data", "network_enabled"),
            ("broker", "live_trading_enabled"),
            ("broker", "execution_enabled"),
            ("broker", "submission_enabled"),
        )
        for section, key in rejected:
            with self.subTest(section=section, key=key):
                candidate = json.loads(json.dumps(baseline))
                candidate[section][key] = True
                with self.assertRaises(ConfigurationError):
                    normalize_manifest(candidate)

    def test_sensitive_and_unknown_fields_are_rejected_not_persisted(self):
        baseline = load_manifest(MANIFEST_PATH)
        for section, key, value in (
            ("broker", "api_key", "secret"),
            ("market_data", "url", "https://key:secret@example.test/feed"),
            ("memory", "training_enabled", True),
        ):
            with self.subTest(key=key):
                candidate = json.loads(json.dumps(baseline))
                candidate[section][key] = value
                with self.assertRaises(ConfigurationError):
                    normalize_manifest(candidate)

    def test_loader_never_uses_network(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network used")) as connect:
            load_manifest(MANIFEST_PATH)
        connect.assert_not_called()

    def test_loader_rejects_symlink_fifo_and_oversized_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            target = directory_path / "target.yaml"
            target.write_bytes(MANIFEST_PATH.read_bytes())
            link = directory_path / "link.yaml"
            link.symlink_to(target)
            with self.assertRaises(ConfigurationError):
                load_manifest(link)

            fifo = directory_path / "manifest.fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ConfigurationError):
                load_manifest(fifo)

            oversized = directory_path / "oversized.yaml"
            oversized.write_bytes(b"{" + b" " * MAX_MANIFEST_BYTES)
            with self.assertRaises(ConfigurationError):
                load_manifest(oversized)


class AuditMemoryTests(unittest.TestCase):
    def test_persists_normalized_versioned_history_without_learning(self):
        config = load_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            store = AuditStore(Path(directory) / "audit.jsonl")
            first = store.record(config)
            second = store.record(config)
            self.assertEqual((first["version"], second["version"]), (1, 2))
            self.assertEqual(first["digest"], second["digest"])
            history = store.history()
            self.assertEqual([item["version"] for item in history], [1, 2])
            self.assertEqual(history[0]["configuration"], config)
            serialized = (Path(directory) / "audit.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("api_key", serialized)
            self.assertNotIn("secret", serialized)
            self.assertNotIn("training", serialized)

    def test_store_refuses_unsafe_data_and_tampered_history(self):
        config = load_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            store = AuditStore(path)
            unsafe = json.loads(json.dumps(config))
            unsafe["broker"]["execution_enabled"] = True
            with self.assertRaises(MemoryError):
                store.record(unsafe)
            self.assertFalse(path.exists())
            path.write_text('{"version":1,"recorded_at":"x","digest":"bad","configuration":{}}\n', encoding="utf-8")
            with self.assertRaises(MemoryError):
                store.history()

    def test_audit_store_rejects_bad_utc_timestamp_and_partial_log(self):
        config = load_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            record = {
                "version": 1,
                "recorded_at": "2026-11-11T18:00:00+02:00",
                "digest": manifest_digest(config),
                "configuration": config,
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaises(MemoryError):
                AuditStore(path).history()

            record["recorded_at"] = "2026-11-11T16:00:00+00:00"
            path.write_text(json.dumps(record), encoding="utf-8")  # crash-partial: no newline
            path.chmod(0o600)
            with self.assertRaises(MemoryError):
                AuditStore(path).history()

    def test_audit_history_is_created_private_and_rejects_unsafe_mode(self):
        config = load_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            store = AuditStore(path)
            store.record(config)
            file_stat = path.stat()
            self.assertTrue(stat.S_ISREG(file_stat.st_mode))
            self.assertEqual(stat.S_IMODE(file_stat.st_mode), 0o600)
            self.assertEqual(file_stat.st_uid, os.geteuid())

            path.chmod(0o644)
            with self.assertRaises(MemoryError):
                store.history()
            with self.assertRaises(MemoryError):
                store.record(config)

            path.chmod(0o600)
            with patch("memory.audit_store.os.geteuid", return_value=os.geteuid() + 1):
                with self.assertRaises(MemoryError):
                    store.history()

    def test_missing_audit_history_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(AuditStore(Path(directory) / "missing.jsonl").history(), [])

    def test_audit_history_rejects_symlink_and_reader_takes_shared_lock(self):
        config = load_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            real_path = directory_path / "real.jsonl"
            AuditStore(real_path).record(config)
            link = directory_path / "link.jsonl"
            link.symlink_to(real_path)
            with self.assertRaises(MemoryError):
                AuditStore(link).history()

            calls = []
            real_flock = fcntl.flock

            def recording_flock(fd, operation):
                calls.append(operation)
                return real_flock(fd, operation)

            with patch("fcntl.flock", side_effect=recording_flock):
                self.assertEqual(len(AuditStore(real_path).history()), 1)
            self.assertIn(fcntl.LOCK_SH, calls)
            self.assertIn(fcntl.LOCK_UN, calls)

    def test_audit_store_never_uses_network(self):
        config = load_manifest(MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(socket, "create_connection", side_effect=AssertionError("network used")) as connect:
                AuditStore(Path(directory) / "audit.jsonl").record(config)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
