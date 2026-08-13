#!/usr/bin/env python3
"""Calculate DORA release metrics from reviewed release evidence JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise ValueError(message)


def timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        fail(f"{field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        fail(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        fail(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        releases = [load(path) for path in args.evidence]
        full = [release for release in releases if release.get("stage") == "full"]
        promoted = [release for release in full if release.get("outcome") == "promoted"]
        failed = [release for release in full if release.get("outcome") in {"blocked", "rolled-back"}]
        lead_times = []
        recovery_times = []
        for index, release in enumerate(releases):
            timestamps = release.get("timestamps", {})
            started = timestamp(timestamps.get("sourceCommittedAt"), f"evidence[{index}].sourceCommittedAt")
            production = timestamp(timestamps.get("productionStartedAt"), f"evidence[{index}].productionStartedAt")
            lead_times.append((production - started).total_seconds())
            failure = timestamps.get("failureDetectedAt")
            rollback = timestamps.get("rollbackCompletedAt")
            if failure is not None or rollback is not None:
                if failure is None or rollback is None:
                    fail(f"evidence[{index}] must provide both failure and rollback timestamps")
                recovery_times.append((timestamp(rollback, f"evidence[{index}].rollbackCompletedAt") - timestamp(failure, f"evidence[{index}].failureDetectedAt")).total_seconds())
        result = {
            "releaseCount": len(releases),
            "fullReleaseCount": len(full),
            "successfulFullReleaseCount": len(promoted),
            "releaseLeadTimeSeconds": lead_times,
            "deploymentFrequency": len(promoted),
            "changeFailureRate": (len(failed) / len(full)) if full else None,
            "recoveryTimeSeconds": recovery_times,
            "definitions": {
                "deploymentFrequency": "successful full-stage releases in supplied evidence set",
                "changeFailureRate": "full-stage releases requiring rollback divided by full-stage releases",
                "releaseLeadTime": "productionStartedAt minus sourceCommittedAt",
                "recoveryTime": "rollbackCompletedAt minus failureDetectedAt",
            },
        }
        encoded = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"DORA metric calculation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
