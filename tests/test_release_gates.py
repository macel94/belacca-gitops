#!/usr/bin/env python3
"""Deterministic tests for release gate validation and safety boundaries."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load("validate_release_gates", ROOT / "scripts/validate-release-gates.py")
runner = load("run_release_gates", ROOT / "scripts/run-release-gates.py")
metrics = load("calculate_dora_metrics", ROOT / "scripts/calculate-dora-metrics.py")
POLICY = json.loads((ROOT / "releases/release-policy.json").read_text())


class ReleaseGateTests(unittest.TestCase):
    def valid_release(self):
        return {
            "releaseId": "release-1",
            "stage": "canary",
            "sourceRevisions": {"pong": "a" * 40, "portfolio": "b" * 40},
            "imageDigests": {"example/image": "sha256:" + "c" * 64},
            "imageReferences": {"example/image": "example/image@sha256:" + "c" * 64},
            "provenance": {
                "verifier": "cosign",
                "attestationType": "https://slsa.dev/provenance/v1",
                "verified": True,
                "verifiedImages": ["example/image"],
                "evidenceUri": "https://evidence.example/attestation/1",
            },
            "fluxRevision": "main@sha1:" + "d" * 40,
            "checks": [
                {"id": check, "target": "https://example.test", "passed": True, "durationMs": 1, "evidence": "https://evidence.example/check/1"}
                for check in validator.CHECKS
            ],
            "outcome": "promoted",
            "timestamps": {
                "sourceCommittedAt": "2026-08-12T12:00:00Z",
                "productionStartedAt": "2026-08-12T12:01:00Z",
            },
        }

    def test_policy_and_canary_are_valid(self):
        validator.validate_policy(POLICY)
        validator.validate_canary()

    def test_mutable_image_is_rejected(self):
        release = self.valid_release()
        release["imageDigests"]["example/image"] = "latest"
        with self.assertRaisesRegex(ValueError, "complete lowercase sha256"):
            validator.validate_release(release, POLICY)

    def test_unverified_provenance_is_rejected(self):
        release = self.valid_release()
        release["provenance"]["verified"] = False
        with self.assertRaisesRegex(ValueError, "provenance"):
            validator.validate_release(release, POLICY)

    def test_provenance_must_cover_every_image(self):
        release = self.valid_release()
        release["imageDigests"]["second/image"] = "sha256:" + "e" * 64
        with self.assertRaisesRegex(ValueError, "imageReferences"):
            validator.validate_release(release, POLICY)

    def test_dora_metrics_calculate_failed_full_release(self):
        release = self.valid_release()
        release["stage"] = "full"
        release["outcome"] = "rolled-back"
        release["rollback"] = {
            "required": True,
            "gitChange": "https://evidence.example/revert",
            "fluxReconciliation": "https://evidence.example/flux",
        }
        release["timestamps"].update({
            "failureDetectedAt": "2026-08-12T12:02:00Z",
            "rollbackCompletedAt": "2026-08-12T12:05:00Z",
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(release))
            self.assertEqual(metrics.main([str(path)]), 0)

    def test_failed_release_requires_reviewed_rollback(self):
        release = self.valid_release()
        release["checks"][0]["passed"] = False
        release["outcome"] = "blocked"
        with self.assertRaisesRegex(ValueError, "rollback"):
            validator.validate_release(release, POLICY)
        release["rollback"] = {
            "required": True,
            "gitChange": "https://github.com/example/repo/commit/revert",
            "fluxReconciliation": "https://evidence.example/flux/1",
        }
        validator.validate_release(release, POLICY)

    def test_runner_argument_parsing_fails_closed_without_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release.json"
            status = runner.main([
                "--release-id", "release-1", "--stage", "canary",
                "--portfolio-url", "https://portfolio.test", "--pong-url", "https://pong.test",
                "--pong-command", "true", "--source", "pong=" + "a" * 40,
                "--image", "example/image=sha256:" + "c" * 64,
                "--flux-revision", "main@sha1:" + "d" * 40,
                "--source-committed-at", "2026-08-12T12:00:00Z",
                "--provenance-evidence", "https://evidence.example/attestation/1",
                "--evidence-uri", "https://evidence.example/release/1",
                "--output", str(output),
            ])
            self.assertEqual(status, 2)
            self.assertFalse(output.exists())

    def test_runner_writes_blocked_evidence_without_leaking_body(self):
        original = runner.request_check
        runner.request_check = lambda url, expected=None: (False, "http-503")
        runner.run_pong = lambda command, url: (False, "runner-exit-1")
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "release.json"
                status = runner.main([
                    "--release-id", "release-1", "--stage", "canary",
                    "--portfolio-url", "https://portfolio.test", "--pong-url", "https://pong.test",
                    "--pong-command", "true", "--source", "pong=" + "a" * 40,
                    "--image", "example/image=sha256:" + "c" * 64,
                    "--flux-revision", "main@sha1:" + "d" * 40,
                    "--source-committed-at", "2026-08-12T12:00:00Z",
                    "--provenance-evidence", "https://evidence.example/attestation/1",
                    "--evidence-uri", "https://evidence.example/release/1",
                    "--readiness-passed", "--provenance-verified", "--output", str(output),
                ])
                self.assertEqual(status, 1)
                evidence = json.loads(output.read_text())
                self.assertEqual(evidence["outcome"], "blocked")
                self.assertTrue(evidence["rollback"]["required"])
                self.assertNotIn("response", output.read_text())
        finally:
            runner.request_check = original


if __name__ == "__main__":
    unittest.main()
