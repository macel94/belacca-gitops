#!/usr/bin/env python3
"""Validate the checked-in service catalog without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "services.json"
REQUIRED_SERVICE_FIELDS = {
    "id",
    "name",
    "owner",
    "publicHosts",
    "tier",
    "dependencies",
    "slo",
    "rto",
    "rpo",
    "dashboard",
    "runbook",
}
REQUIRED_SLO_FIELDS = {"status", "target", "window", "indicator", "measurement"}
REQUIRED_DASHBOARD_FIELDS = {"url", "access"}
DNS_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
VALID_TIERS = {"tier-1", "tier-2", "tier-3"}
VALID_SLO_STATUSES = {"proposed", "measured", "retired"}


def fail(message: str) -> None:
    raise ValueError(message)


def require_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")


def main() -> int:
    try:
        with CATALOG.open(encoding="utf-8") as handle:
            catalog = json.load(handle)
        if catalog.get("apiVersion") != "belacca.com/v1alpha1":
            fail("apiVersion must be belacca.com/v1alpha1")
        if catalog.get("kind") != "ServiceCatalog":
            fail("kind must be ServiceCatalog")
        if not isinstance(catalog.get("services"), list) or not catalog["services"]:
            fail("services must be a non-empty list")

        ids: set[str] = set()
        for index, service in enumerate(catalog["services"]):
            prefix = f"services[{index}]"
            if not isinstance(service, dict):
                fail(f"{prefix} must be an object")
            missing = REQUIRED_SERVICE_FIELDS - service.keys()
            if missing:
                fail(f"{prefix} missing fields: {', '.join(sorted(missing))}")
            service_id = service["id"]
            require_string(service_id, f"{prefix}.id")
            if service_id in ids:
                fail(f"duplicate service id: {service_id}")
            ids.add(service_id)
            for field in ("name", "owner", "tier", "rto", "rpo", "runbook", "implementation"):
                if field in service:
                    require_string(service[field], f"{prefix}.{field}")
            if service["tier"] not in VALID_TIERS:
                fail(f"{prefix}.tier must be one of {sorted(VALID_TIERS)}")
            hosts = service["publicHosts"]
            if not isinstance(hosts, list) or not hosts:
                fail(f"{prefix}.publicHosts must be a non-empty list")
            for host in hosts:
                require_string(host, f"{prefix}.publicHosts entry")
                if not DNS_NAME.fullmatch(host) or ".." in host:
                    fail(f"invalid public host in {prefix}: {host}")
            dependencies = service["dependencies"]
            if not isinstance(dependencies, list) or not dependencies:
                fail(f"{prefix}.dependencies must be a non-empty list")
            for dep_index, dependency in enumerate(dependencies):
                if not isinstance(dependency, dict) or set(dependency) != {"name", "kind", "required"}:
                    fail(f"{prefix}.dependencies[{dep_index}] must have name, kind, required")
                require_string(dependency["name"], f"{prefix}.dependencies[{dep_index}].name")
                require_string(dependency["kind"], f"{prefix}.dependencies[{dep_index}].kind")
                if not isinstance(dependency["required"], bool):
                    fail(f"{prefix}.dependencies[{dep_index}].required must be boolean")
            slo = service["slo"]
            if not isinstance(slo, dict) or not REQUIRED_SLO_FIELDS <= slo.keys():
                fail(f"{prefix}.slo missing fields: {', '.join(sorted(REQUIRED_SLO_FIELDS))}")
            if slo["status"] not in VALID_SLO_STATUSES:
                fail(f"{prefix}.slo.status must be one of {sorted(VALID_SLO_STATUSES)}")
            for field in REQUIRED_SLO_FIELDS - {"status"}:
                require_string(slo[field], f"{prefix}.slo.{field}")
            dashboard = service["dashboard"]
            if not isinstance(dashboard, dict) or not REQUIRED_DASHBOARD_FIELDS <= dashboard.keys():
                fail(f"{prefix}.dashboard missing fields: {', '.join(sorted(REQUIRED_DASHBOARD_FIELDS))}")
            require_string(dashboard["url"], f"{prefix}.dashboard.url")
            if not dashboard["url"].startswith("https://"):
                fail(f"{prefix}.dashboard.url must use https")
            require_string(dashboard["access"], f"{prefix}.dashboard.access")

        expected = {"portfolio", "pong", "analytics", "dashboard"}
        if ids != expected:
            fail(f"catalog services must be exactly {sorted(expected)}, got {sorted(ids)}")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"catalog validation failed: {error}", file=sys.stderr)
        return 1

    print(f"validated {len(ids)} services in {CATALOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
