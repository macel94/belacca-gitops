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

    def test_safe_prefix_rejects_path_traversal(self) -> None:
        with self.assertRaises(SystemExit):
            backup_runner.safe_prefix("approved/../other")


if __name__ == "__main__":
    unittest.main()
