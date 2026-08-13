#!/usr/bin/env python3
"""Validate native recovery and backup contracts without contacting a cluster."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "BACKUP-CONTRACT.md"
DRILLS = ROOT / "docs" / "GAME-DAY-DRILLS.md"

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
    "CronJobs are committed in a fail-closed state",
    "pong-api-data",
)
REQUIRED_DRILL_MARKERS = (
    "# Native production game-day drills",
    "belacca-native",
    "Public-edge",
    "Control-plane/server failure",
    "Longhorn",
    "rollback",
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
        for marker in REQUIRED_DRILL_MARKERS:
            if marker not in drills:
                fail(f"native game-day drills are missing marker: {marker}")
        if re.search(r"(?im)^\s*(?:address|endpoint|bucket|access-key-id|secret-access-key|kms-key-id):\s*https?://|^\s*(?:access-key-id|secret-access-key|kms-key-id):\s*[^<`\s]+", contract):
            fail("backup contract appears to contain a credential or endpoint value")
        if "do not upload" not in contract.lower() and "does not upload" not in contract.lower():
            fail("backup contract must state that the checked-in helper does not upload")
    except (OSError, ValueError) as error:
        print(f"recovery contract validation failed: {error}", file=sys.stderr)
        return 1
    print("validated native recovery contract and game-day drill markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
