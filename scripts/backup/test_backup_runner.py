#!/usr/bin/env python3
"""Deterministic local tests for the dependency-free backup runner."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import backup_runner


class BackupRunnerTests(unittest.TestCase):
    def test_online_backup_preserves_rows_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite"
            destination = root / "destination.sqlite"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
                db.execute("INSERT INTO evidence VALUES ('stable')")
            backup_runner.online_backup(source, destination)
            backup_runner.integrity(destination)
            with sqlite3.connect(destination) as db:
                self.assertEqual(db.execute("SELECT value FROM evidence").fetchone(), ("stable",))

    def test_manifest_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.sqlite"
            with sqlite3.connect(artifact) as db:
                db.execute("CREATE TABLE evidence (value TEXT)")
            data = backup_runner.metadata("pong", artifact, "revision", "image@sha256:digest")
            data["source_sha256"] = "0" * 64
            with self.assertRaises(SystemExit):
                backup_runner.validate_manifest(data, "pong", artifact)

    def test_object_lock_put_checksum_is_base64_md5(self) -> None:
        self.assertEqual(
            backup_runner.content_md5(b"permission-test"),
            "6ndHq1GLfHFm943fUZ7ddg==",
        )

    def test_verify_can_suppress_nested_machine_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.sqlite"
            with sqlite3.connect(artifact) as db:
                db.execute("CREATE TABLE evidence (value TEXT)")
            backup_runner.verify("pong", artifact, emit=False)

    def test_safe_prefix_rejects_path_traversal(self) -> None:
        with self.assertRaises(SystemExit):
            backup_runner.safe_prefix("approved/../other")

    def test_metrics_configuration_is_unknown_until_external_restore_inputs_exist(self) -> None:
        names = (
            "BACKUP_AUTOMATION_ENABLED", "BACKUP_CONSISTENCY_ACKNOWLEDGED",
            "S3_RESTORE_ENDPOINT", "S3_RESTORE_BUCKET", "S3_RESTORE_PREFIX",
            "S3_RESTORE_REGION", "S3_RESTORE_ACCESS_KEY_ID", "S3_RESTORE_SECRET_ACCESS_KEY",
        )
        original = {name: backup_runner.os.environ.pop(name, None) for name in names}
        try:
            self.assertFalse(backup_runner.restore_configuration_ready())
            backup_runner.os.environ.update({
                "BACKUP_AUTOMATION_ENABLED": "true",
                "BACKUP_CONSISTENCY_ACKNOWLEDGED": "true",
                "S3_RESTORE_ENDPOINT": "https://objects.example.test",
                "S3_RESTORE_BUCKET": "backups",
                "S3_RESTORE_PREFIX": "native",
                "S3_RESTORE_REGION": "us-east-1",
                "S3_RESTORE_ACCESS_KEY_ID": "access",
                "S3_RESTORE_SECRET_ACCESS_KEY": "secret",
            })
            self.assertTrue(backup_runner.restore_configuration_ready())
        finally:
            for name in names:
                backup_runner.os.environ.pop(name, None)
                if original[name] is not None:
                    backup_runner.os.environ[name] = original[name]


if __name__ == "__main__":
    unittest.main()
