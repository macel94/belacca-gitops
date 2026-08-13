#!/usr/bin/env python3
"""Validate the staged, plain-Prometheus observability contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "clusters" / "belacca-production" / "observability"
NATIVE_OBS = OBS
NATIVE_PLATFORM_APPLICATIONS = ROOT / "clusters" / "belacca-production" / "native-platform-applications.yaml"
RUNBOOK = ROOT / "docs" / "NATIVE-OBSERVABILITY-RUNBOOK.md"
RULE_TEST = ROOT / "tests" / "prometheus" / "native-observability.yml"


def fail(message: str) -> None:
    raise ValueError(message)


def validate_native() -> None:
    """Validate the sole maintained native observability child."""
    synthetic = json.loads((NATIVE_OBS / "synthetic-contracts.json").read_text())
    config = (NATIVE_OBS / "config.yaml").read_text()
    deployment = (NATIVE_OBS / "deployment.yaml").read_text()
    pvc = (NATIVE_OBS / "pvc.yaml").read_text()
    policies = (NATIVE_OBS / "network-policy.yaml").read_text()
    flux = NATIVE_PLATFORM_APPLICATIONS.read_text()

    if synthetic.get("environment") != "native-production":
        fail("native synthetic contract must identify native production")
    if synthetic.get("availability_policy") != "Each public service targets 99% availability over 30d; this is not an SLA.":
        fail("native contract must state the 99%/30d no-SLA policy")
    source = synthetic.get("external_slo_source")
    if not isinstance(source, dict) or source.get("status") != "proposed":
        fail("native contract must keep the external SLO source proposed")
    if source.get("ingested_into_prometheus") is not False or source.get("status_repository_scraped") is not False:
        fail("native contract must not claim status-repository Prometheus scraping")
    boundary = source.get("ingestion_boundary")
    if not isinstance(boundary, dict) or boundary.get("deployment_status") != "contract-only/not-deployed":
        fail("native contract must keep the ingestion boundary inactive until provisioned")
    if boundary.get("metric") != "belacca_slo_observation_events_total" or boundary.get("cadence") != "1h":
        fail("native SLO boundary must define the hourly counter metric")
    labels = boundary.get("allowed_labels")
    if labels != {
        "service": ["portfolio", "pong", "analytics"],
        "outcome": ["good", "bad"],
    }:
        fail("native SLO boundary labels must be bounded to the approved service/outcome values")
    if "Exactly one increment" not in boundary.get("required_event", ""):
        fail("native SLO boundary must define one event per valid hourly observation")
    checks = synthetic.get("checks")
    if not isinstance(checks, list) or {item.get("service") for item in checks} != {
        "portfolio", "pong", "analytics", "dashboard"
    }:
        fail("native synthetic contract must cover portfolio, pong, analytics, dashboard")
    for item in checks:
        if item.get("service") == "dashboard":
            if item.get("slo_eligible") is not False or item.get("deployment_status") != "external-only/not-deployed":
                fail("native dashboard check must remain proposed and external-only/not-deployed")
            if item.get("credentials_in_git") is not False:
                fail("native dashboard synthetic must keep credentials out of Git")
    privacy = synthetic.get("privacy", {})
    for field in (
        "store_room_ids",
        "store_player_names",
        "store_client_addresses",
        "store_tokens",
        "store_response_bodies",
    ):
        if privacy.get(field) is not False:
            fail(f"native synthetic contract must prohibit {field}")

    required_fragments = (
        "cluster: belacca-native",
        "job_name: native-pong-api-diagnostic",
        "pong-api.pong.svc.cluster.local:8080",
        "job_name: native-flux-controllers-diagnostic",
        "source-controller.flux-system.svc.cluster.local:80",
        "sample_limit: 100",
        "sample_limit: 500",
        "job_name: native-slo-evidence-boundary",
        "slo-evidence-adapter.observability.svc.cluster.local:8080",
        "belacca_slo_observation_events_total",
        "regex: portfolio|pong|analytics",
        "regex: good|bad",
        "record: belacca:slo_source:external_probe:coverage",
        "expr: vector(0)",
    )
    for fragment in required_fragments:
        if fragment not in config:
            fail(f"native observability config missing {fragment!r}")
    rules = config.split("  prometheus.rules.yml: |", 1)[-1]
    if re.search(r"(?im)^\s*expr:.*(?:availability|recovery|drill)", rules):
        fail("native recording rules must not calculate availability or recovery drills")
    if not re.search(r"(?m)^\s*-?\s*record: belacca:native:pong:http_requests:rate5m$", rules):
        fail("native Pong diagnostic recording rule is missing")
    for record in (
        "belacca:slo:good_events:30d",
        "belacca:slo:total_events:30d",
        "belacca:slo:sli:30d",
        "belacca:slo:error_budget:30d",
        "belacca:slo:data_coverage:30d",
    ):
        if not re.search(rf"(?m)^\s*-?\s*record: {re.escape(record)}$", rules):
            fail(f"native SLO recording rule is missing: {record}")
    if not re.search(r"(?m)^\s*-?\s*record: belacca:native:flux:reconciliation_failures:rate5m$", rules):
        fail("native Flux diagnostic recording rule is missing")
    if "increase(belacca_slo_observation_events_total{outcome=~\"good|bad\"}[30d])" not in rules:
        fail("native total events must use sanitized good/bad evidence")
    if "data_coverage:30d == 1" not in rules or "total_events:30d > 0" not in rules:
        fail("native SLI and error budget must fail closed on missing/partial data")

    if "prom/prometheus:v3.13.2@sha256:" not in deployment or re.search(r"image:\s+\S+:latest(?:\s|$)", deployment):
        fail("native Prometheus image must be immutable and must not use latest")
    for fragment in (
        "--storage.tsdb.retention.time=45d",
        "--storage.tsdb.retention.size=4GB",
        "claimName: prometheus-native-data",
        "requests:\n              cpu: 100m",
        "limits:\n              cpu: 500m",
        "type: ClusterIP",
    ):
        if fragment not in deployment:
            fail(f"native deployment missing {fragment}")
    for fragment in (
        "storageClassName: longhorn",
        "ReadWriteOnce",
        "storage: 5Gi",
    ):
        if fragment not in pvc:
            fail(f"native Prometheus PVC missing {fragment}")
    if "retention.time=45d" not in deployment:
        fail("native retention must exceed the 30-day SLO window")

    for fragment in (
        "k8s-app: kube-dns",
        "kubernetes.io/metadata.name: pong",
        "app: cloudnativepong",
        "component: api",
        "kubernetes.io/metadata.name: flux-system",
        "app: source-controller",
        "app: kustomize-controller",
        "app: helm-controller",
        "app: notification-controller",
        "kubernetes.io/metadata.name: headlamp",
        "app.kubernetes.io/name: headlamp",
        "app.kubernetes.io/instance: headlamp",
        "port: 9090",
    ):
        if fragment not in policies:
            fail(f"native NetworkPolicy missing narrow private rule {fragment}")
    if "0.0.0.0/0" in policies or re.search(r"type:\s+(?:NodePort|LoadBalancer)", deployment):
        fail("native observability must not be publicly exposed")
    if "slo-evidence-adapter.observability.svc.cluster.local" not in config:
        fail("native config must retain the private external-evidence ingestion boundary")

    native_files = list(NATIVE_OBS.glob("*"))
    for path in native_files:
        text = path.read_text()
        if "clusters/belacca-production" not in flux and path.name == "config.yaml":
            fail(f"native observability is not wired to the native production tree: {path}")
        if re.search(r"image:\s+\S+:latest(?:\s|$)", text):
            fail(f"native observability contains a mutable latest image: {path}")
        if re.search(r"kind:\s+Ingress|type:\s+(?:NodePort|LoadBalancer)", text):
            fail(f"native observability contains public exposure: {path}")
        if path.name == "config.yaml" and re.search(r"room_id|player_name|client_address|request_id|token", text, re.IGNORECASE):
            fail(f"native observability config contains a forbidden high-cardinality/private field: {path}")
    for fragment in (
        "name: native-observability",
        "path: ./clusters/belacca-production/observability",
        "prune: false",
        "wait: true",
        "dependsOn:\n    - name: flux-system",
    ):
        if fragment not in flux:
            fail(f"native Flux wiring missing {fragment}")
    runbook = RUNBOOK.read_text()
    for fragment in (
        "belacca-native",
        "prometheus-native",
        "native-slo-evidence-boundary",
        "belacca_slo_observation_events_total",
        "45 days and 4GiB",
        "Missing, malformed, or partial",
        "native production",
    ):
        if fragment not in runbook:
            fail(f"native observability runbook is missing {fragment!r}")
    test = RULE_TEST.read_text()
    for fragment in (
        "missing_external_evidence_is_not_success",
        "exp_samples: []",
        "belacca:slo:data_coverage:30d",
    ):
        if fragment not in test:
            fail(f"native Prometheus rule test is missing {fragment!r}")


def main() -> int:
    try:
        validate_native()

    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"observability validation failed: {error}")
        return 1

    print("validated native observability config, contracts, and dashboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
