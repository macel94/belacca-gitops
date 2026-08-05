#!/usr/bin/env python3
"""Validate the staged, plain-Prometheus observability contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "clusters" / "vmi3474918" / "observability"


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> int:
    try:
        synthetic = json.loads((OBS / "synthetic-contracts.json").read_text())
        dashboard = json.loads((OBS / "dashboard.json").read_text())
        config = (OBS / "config.yaml").read_text()
        deployment = (OBS / "deployment.yaml").read_text()

        if synthetic.get("contract_version") != "belacca.synthetic-contracts.v1":
            fail("unexpected synthetic contract version")
        checks = synthetic.get("checks")
        if not isinstance(checks, list) or {item.get("service") for item in checks} != {
            "portfolio", "pong", "analytics", "dashboard"
        }:
            fail("synthetic contract must cover portfolio, pong, analytics, dashboard")
        if synthetic.get("privacy", {}).get("store_tokens") is not False:
            fail("synthetic contract must prohibit token storage")
        for item in checks:
            if item.get("service") == "dashboard" and item.get("credentials_in_git") is not False:
                fail("dashboard synthetic must keep credentials out of Git")

        if dashboard.get("dashboard", {}).get("title") != "Belacca Platform Reliability (staged)":
            fail("unexpected dashboard title")
        panels = dashboard.get("dashboard", {}).get("panels")
        if not isinstance(panels, list) or not panels:
            fail("dashboard must define at least one panel")
        for panel in panels:
            if not isinstance(panel.get("query"), str) or "{" in panel["query"] and "}" in panel["query"] and "room" in panel["query"]:
                fail("dashboard query contains an unsafe/high-cardinality room selector")

        required_fragments = (
            "scrape_configs:",
            "rule_files:",
            "sample_limit: 100",
            "sample_limit: 500",
            "pong-api.pong.svc.cluster.local:8080",
            "source-controller.flux-system.svc.cluster.local:80",
        )
        for fragment in required_fragments:
            if fragment not in config:
                fail(f"observability config missing {fragment!r}")
        if "latest" in config or "prom/prometheus:v3.13.2@sha256:" not in deployment:
            fail("Prometheus image must be pinned and must not use latest")
        for fragment in ("--storage.tsdb.retention.time=7d", "--storage.tsdb.retention.size=2GB"):
            if fragment not in deployment:
                fail(f"deployment missing {fragment}")

    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"observability validation failed: {error}")
        return 1

    print("validated staged observability config, contracts, and dashboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
