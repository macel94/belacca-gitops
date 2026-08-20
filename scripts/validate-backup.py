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
            group = {"pong": "1000", "goatcounter": "1000", "dex": "1001"}[service]
            require(source_jobs, f"fsGroup: {group}", f"{service} source filesystem group")
            identity_name = {"pong": "pong-backup-writer", "goatcounter": "analytics-backup-writer", "dex": "dex-backup-writer"}[service]
            require(identities, f"name: {identity_name}", "writer identities")
        for marker in (
            "app: cloudnativepong",
            "app: goatcounter",
            "app.kubernetes.io/name: dex",
            "topologyKey: kubernetes.io/hostname",
        ):
            require(source_jobs, marker, "source Job same-node PVC affinity")
        if source_jobs.count("podAffinity:") != 3 or source_jobs.count("requiredDuringSchedulingIgnoredDuringExecution:") != 3:
            fail("each source Job must require affinity with its single-writer workload")
        for service in ("pong", "goatcounter", "dex"):
            require(verifier, f"name: {service}-restore-verification", "restore Jobs")
            require(verifier, f'"restore-verify", "{service}"', "restore Jobs")
        require(verifier, "namespace: backup-system", "restore Jobs")
        # ResourceQuota requires every backup-system Pod to declare CPU
        # requests and memory limits. Keep the three scheduled verifiers and
        # the metrics Deployment within the bounded namespace budget.
        if verifier.count("requests: {cpu: 25m, memory: 64Mi}") != 3:
            fail("each restore verifier must declare the bounded resource request")
        if verifier.count("limits: {memory: 256Mi}") != 3:
            fail("each restore verifier must declare the bounded memory limit")
        if "requests: {cpu: 50m, memory: 128Mi}" not in verifier or "limits: {memory: 512Mi}" not in verifier:
            fail("backup metrics Deployment must declare the bounded CPU request and memory limit")
        for marker in (
            "name: BACKUP_AUTOMATION_ENABLED, valueFrom: {secretKeyRef: {name: backup-restore-runtime, key: automation-enabled, optional: true}}",
            "name: BACKUP_CONSISTENCY_ACKNOWLEDGED, valueFrom: {secretKeyRef: {name: backup-restore-runtime, key: consistency-acknowledged, optional: true}}",
            "name: S3_RESTORE_ENDPOINT, valueFrom: {secretKeyRef: {name: backup-restore-object-store, key: endpoint, optional: true}}",
            "name: S3_RESTORE_SECRET_ACCESS_KEY, valueFrom: {secretKeyRef: {name: backup-restore-object-store, key: secret-access-key, optional: true}}",
        ):
            require(verifier, marker, "backup metrics Secret interface")
        require(verifier, "belacca.com/runner-contract: configuration-aware-v2", "backup metrics contract")
        for service_label in ("exported_service",):
            if observability.count(f"{{{{ $labels.{service_label} }}}}") < 4:
                fail("backup alerts must identify the exported service label")
        if re.search(r"restore-verification[\s\S]*?claimName:", verifier):
            fail("restore verification must not mount a production PVC")

        for text, label in ((source_jobs, "source Jobs"), (verifier, "restore Jobs")):
            if text.count("concurrencyPolicy: Forbid") < 3 and label == "source Jobs":
                fail("each source Job must forbid overlap")
            if text.count("failedJobsHistoryLimit: 0") != 3:
                fail(f"each {label} CronJob must disable failed Job history retention")
            if text.count("ttlSecondsAfterFinished: 900") != 3:
                fail(f"each {label} Job must expire 15 minutes after completion")
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
            "NativeBackupConfigurationUnknown",
            "belacca_backup_configuration_ready",
            "NativeBackupUploadOrVerificationMissing",
            "backup-metrics.backup-system.svc.cluster.local:9091",
        ):
            require(observability, marker, "observability contract")
        for alert, expression in (
            ("NativeBackupStale", "(time() - belacca_backup_last_success_timestamp_seconds > 93600) and on() (belacca_backup_configuration_ready == 1)"),
            ("NativeBackupIntegrityFailed", "(belacca_backup_integrity_ok < 1) and on() (belacca_backup_configuration_ready == 1)"),
            ("NativeBackupDailyRetentionLow", "(belacca_backup_daily_retention_count < 35) and on() (belacca_backup_configuration_ready == 1)"),
            ("NativeBackupMonthlyRetentionLow", "(belacca_backup_monthly_retention_count < 12) and on() (belacca_backup_configuration_ready == 1)"),
        ):
            require(observability, f"alert: {alert}", "observability contract")
            require(observability, f"expr: {expression}", f"{alert} readiness gate")
        require(policy, "backup-metrics", "backup NetworkPolicy")
        require(flux, "name: native-backup", "Flux wiring")
        require(flux, "path: ./clusters/belacca-production/backup", "Flux wiring")
        require((cluster / "kustomization.yaml").read_text(), "  - backup\n", "native root")
        runner = RUNNER.read_text()
        for marker in (
            "sqlite3",
            "source_db.backup(",
            "BACKUP_PAGE_SIZE = 64",
            "BACKUP_LOCK_TIMEOUT_SECONDS = 120",
            "BACKUP_MAX_ATTEMPTS = 2",
            "progress=progress",
            "x-amz-server-side-encryption",
            "content-md5",
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
