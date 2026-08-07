#!/usr/bin/env python3
"""Validate the checked-in recovery contract without contacting a cluster."""

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
    "No CronJob is committed",
    "k3d-pong",
    "pong-api-data",
)
REQUIRED_DRILL_HEADINGS = (
    "## Old production gateway failure",
    "## Old production static service failure",
    "## Old production lobby/API failure",
    "## Old production dynamic room failure",
    "## Old production Flux reconciliation failure",
    "## Old production NetworkPolicy failure",
    "## Old production rollback command index",
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
        for heading in REQUIRED_DRILL_HEADINGS:
            if heading not in drills:
                fail(f"game-day drills are missing heading: {heading}")
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
