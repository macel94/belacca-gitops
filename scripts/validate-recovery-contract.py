#!/usr/bin/env python3
"""Validate the checked-in recovery contract without contacting a cluster."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "BACKUP-CONTRACT.md"
DRILLS = ROOT / "docs" / "GAME-DAY-DRILLS.md"
HISTORICAL_DRILLS = ROOT / "docs" / "GAME-DAY-DRILLS-HISTORICAL.md"
EVIDENCE = ROOT / "docs" / "native-game-day-evidence.json"
REVIEW = ROOT / "docs" / "NATIVE-GAME-DAY-ISSUE-4-REVIEWED.md"
SAFETY_GATE = ROOT / "scripts" / "native-game-day.py"

REQUIRED_CONTRACT_MARKERS = (
    "35 daily verified backups",
    "12 monthly verified backups",
    "TLS is required",
    "pong-backup-object-store",
    "pong-backup-encryption",
    "pong-backup-restore-object-store",
    "endpoint",
    "bucket",
    "secret-access-key",
    "kms-key-id",
    "No CronJob is committed",
    "k3d-pong",
    "pong-api-data",
)
REQUIRED_NATIVE_DRILL_HEADINGS = (
    "## Drill 1 — one public edge unavailable",
    "## Drill 2 — one control-plane/server unavailable",
    "## Drill 3 — Pong API restart with SQLite PVC preserved",
    "## Drill 4 — Longhorn replica/node degradation",
    "## Drill 5 — failed application reconciliation and Git rollback",
    "## Drill 6 — external synthetic recovery verification",
)
REQUIRED_NATIVE_MARKERS = (
    "belacca-native",
    "Preconditions",
    "Abort criteria",
    "exact scope",
    "expected impact",
    "**Rollback:**",
    "Detection",
    "Acknowledgement",
    "Mitigation",
    "Recovery",
    "User impact",
    "pong-api-data",
    "goatcounter-data",
    "dex-data",
    "99% availability over 30 days",
    "not-executed-production-access-unavailable",
)


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> int:
    try:
        contract = CONTRACT.read_text(encoding="utf-8")
        drills = DRILLS.read_text(encoding="utf-8")
        for marker in REQUIRED_CONTRACT_MARKERS:
            if marker not in contract:
                fail(f"backup contract is missing required marker: {marker}")
        for heading in REQUIRED_NATIVE_DRILL_HEADINGS:
            if heading not in drills:
                fail(f"native game-day drills are missing heading: {heading}")
        for marker in REQUIRED_NATIVE_MARKERS:
            if marker not in drills:
                fail(f"native game-day runbook is missing marker: {marker}")
        historical = HISTORICAL_DRILLS.read_text(encoding="utf-8")
        if "k3d-pong" not in historical or "not valid production commands" not in historical:
            fail("historical drill copy is not clearly marked retired")
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        if evidence.get("issue") != 4 or evidence.get("environment") != "native-production":
            fail("evidence record has the wrong issue or environment")
        if evidence.get("execution_status") != "not-executed-production-access-unavailable":
            fail("evidence record must not claim production execution")
        if evidence.get("review", {}).get("reviewed") is not True:
            fail("sanitized implementation evidence must be reviewed")
        drills_in_evidence = evidence.get("drills", [])
        if len(drills_in_evidence) != 6:
            fail("evidence record must contain exactly six native drills")
        for drill in drills_in_evidence:
            if drill.get("status") != "not-executed":
                fail("checked-in evidence must not claim a drill was executed")
            if drill.get("sanitization_review", {}).get("reviewed") is not False:
                fail("unexecuted drill entries must remain awaiting production review")
        review = REVIEW.read_text(encoding="utf-8")
        review_normalized = re.sub(r"\s+", " ", review)
        for marker in ("production execution is not claimed", "99%/30-day policy", "Exact operator follow-up"):
            if marker not in review_normalized:
                fail(f"reviewed evidence record is missing marker: {marker}")
        safety_gate = SAFETY_GATE.read_text(encoding="utf-8")
        for marker in ("belacca-native", "pong-api-data", "--wait=false", "PROTECTED_PVCS"):
            if marker not in safety_gate:
                fail(f"native safety gate is missing marker: {marker}")
        if re.search(r"kubectl[^\n]*(?:delete|patch|apply)[^\n]*pvc", safety_gate, re.IGNORECASE):
            fail("native safety gate contains a PVC mutation command")
        if re.search(r"(?im)^\s*(?:address|endpoint|bucket|access-key-id|secret-access-key|kms-key-id):\s*https?://|^\s*(?:access-key-id|secret-access-key|kms-key-id):\s*[^<`\s]+", contract):
            fail("backup contract appears to contain a credential or endpoint value")
        in_fenced_block = False
        for line in contract.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("```"):
                in_fenced_block = not in_fenced_block
                continue
            if in_fenced_block and re.search(
                r"(?:^|[` ])k3d cluster delete\s+(?:pong|k3d-pong)(?:[` ]|$)|"
                r"kubectl[^\n]*delete\s+(?:pvc|namespace)[^\n]*(?:pong|k3d-pong)",
                stripped,
            ):
                fail("backup contract contains an executable destructive production command")
        if "do not upload" not in contract.lower() and "does not upload" not in contract.lower():
            fail("backup contract must state that the checked-in helper does not upload")
    except (OSError, ValueError) as error:
        print(f"recovery contract validation failed: {error}", file=sys.stderr)
        return 1
    print("validated recovery contract and game-day drill markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
