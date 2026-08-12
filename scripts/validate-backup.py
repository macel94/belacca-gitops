#!/usr/bin/env python3
"""Validate the checked-in native encrypted-backup implementation."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "clusters" / "belacca-production" / "backup"
RUNNER = ROOT / "scripts" / "backup" / "backup_runner.py"
CONTRACT = ROOT / "docs" / "BACKUP-RUNBOOK.md"


def fail(message: str) -> None:
    raise ValueError(message)


def require(text: str, marker: str, label: str) -> None:
    if marker not in text:
        fail(f"{label} is missing {marker!r}")


def main() -> int:
    try:
        kustomization = (BACKUP / "kustomization.yaml").read_text()
        source_jobs = (BACKUP / "source-jobs.yaml").read_text()
        identities = (BACKUP / "serviceaccount.yaml").read_text()
        verifier = (BACKUP / "restore-verifier.yaml").read_text()
        policy = (BACKUP / "network-policy.yaml").read_text()
        cluster = ROOT / "clusters" / "belacca-production"
        flux = (cluster / "native-platform-applications.yaml").read_text()
        observability = (cluster / "observability" / "config.yaml").read_text()
        runbook = CONTRACT.read_text()
        local_runner = (BACKUP / "backup_runner.py").read_bytes()
        canonical_runner = RUNNER.read_bytes()

        if local_runner != canonical_runner:
            fail("Kustomize-local runner is not byte-for-byte identical to canonical runner")
        for service, namespace, pvc, path in (
            ("pong", "pong", "pong-api-data", "/source/pong.db"),
            ("goatcounter", "analytics", "goatcounter-data", "/source/db.sqlite3"),
            ("dex", "dex", "dex-data", "/source/dex.db"),
        ):
            require(source_jobs, f"name: {service}-backup", "source Jobs")
            require(source_jobs, f"namespace: {namespace}", "source Jobs")
            require(source_jobs, f"claimName: {pvc}", "source Jobs")
            require(source_jobs, path, "source Jobs")
            identity_name = {"pong": "pong-backup-writer", "goatcounter": "analytics-backup-writer", "dex": "dex-backup-writer"}[service]
            require(identities, f"name: {identity_name}", "writer identities")
        for service in ("pong", "goatcounter", "dex"):
            require(verifier, f"name: {service}-restore-verification", "restore Jobs")
            require(verifier, f'"restore-verify", "{service}"', "restore Jobs")
        require(verifier, "namespace: backup-system", "restore Jobs")
        if re.search(r"restore-verification[\s\S]*?claimName:", verifier):
            fail("restore verification must not mount a production PVC")

        for text, label in ((source_jobs, "source Jobs"), (verifier, "restore Jobs")):
            if text.count("concurrencyPolicy: Forbid") < 3 and label == "source Jobs":
                fail("each source Job must forbid overlap")
            require(text, "startingDeadlineSeconds: 3600", label)
            require(text, "activeDeadlineSeconds: 1800", label)
            require(text, "automountServiceAccountToken: false", label)
            require(text, "python:3.13.11-slim-bookworm@sha256:", label)
        for gate in ("BACKUP_AUTOMATION_ENABLED", "BACKUP_CONSISTENCY_ACKNOWLEDGED"):
            require(source_jobs, gate, "source gate")
            require(verifier, gate, "restore gate")
        for marker in ("PutObject", "GetObject", "DeleteObject", "SSE-KMS", "WORM", "35", "12", "AccessDenied"):
            require(runbook, marker, "runbook")
        for marker in (
            "belacca_backup_last_success_timestamp_seconds",
            "belacca_backup_integrity_ok",
            "belacca_backup_daily_retention_count",
            "belacca_backup_monthly_retention_count",
            "NativeBackupStale",
            "NativeBackupIntegrityFailed",
            "NativeBackupDailyRetentionLow",
            "NativeBackupMonthlyRetentionLow",
            "NativeBackupUploadOrVerificationMissing",
            "backup-metrics.backup-system.svc.cluster.local:9091",
        ):
            require(observability, marker, "observability contract")
        require(policy, "backup-metrics", "backup NetworkPolicy")
        require(flux, "name: native-backup", "Flux wiring")
        require(flux, "path: ./clusters/belacca-production/backup", "Flux wiring")
        require((cluster / "kustomization.yaml").read_text(), "  - backup\n", "native root")
        runner = RUNNER.read_text()
        for marker in (
            "sqlite3",
            "source_db.backup(destination_db)",
            "x-amz-server-side-encryption",
            "https://",
            '"belacca.backup.v1"',
            '"source_sha256"',
            '"source_revision"',
            '"image_digests"',
            '"isolated_target": True',
        ):
            require(runner, marker, "backup runner")
        if re.search(r"(?:access-key-id|secret-access-key|kms-key-id):\s*[^<{`\s]+", "\n".join(p.read_text(errors="ignore") for p in BACKUP.glob("*.yaml"))):
            fail("backup manifests contain a credential-like value")
    except (OSError, ValueError) as error:
        print(f"backup validation failed: {error}", file=sys.stderr)
        return 1
    print("validated native encrypted backup, restore verification, safety gates, and alerts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
