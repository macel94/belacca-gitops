#!/usr/bin/env python3
"""Validate the native NetworkPolicy contract without contacting a cluster."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "clusters" / "belacca-production" / "policies"
CONTRACT = POLICIES / "edge-contract.json"
BUNDLE = POLICIES / "network-policies.yaml"
KUSTOMIZATION = POLICIES / "kustomization.yaml"
PLATFORM = ROOT / "clusters" / "belacca-production" / "native-platform-applications.yaml"
LONGHORN = ROOT / "clusters" / "belacca-production" / "longhorn" / "helmrelease.yaml"
DEX = ROOT / "clusters" / "belacca-production" / "dex" / "network-policy.yaml"
ANALYTICS = ROOT / "clusters" / "belacca-production" / "analytics" / "network-policy.yaml"
NATIVE_NETWORK_POLICIES = tuple((ROOT / "clusters" / "belacca-production").rglob("network-policy*.yaml"))
PROBE = ROOT / "scripts" / "verify-native-network-policy.sh"
RUNBOOK = ROOT / "docs" / "NATIVE-NETWORK-POLICY.md"


def fail(message: str) -> None:
    raise ValueError(message)


def require(text: str, fragments: tuple[str, ...], label: str) -> None:
    for fragment in fragments:
        if fragment not in text:
            fail(f"{label} is missing {fragment!r}")


def main() -> int:
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        bundle = BUNDLE.read_text(encoding="utf-8")
        platform = PLATFORM.read_text(encoding="utf-8")
        longhorn = LONGHORN.read_text(encoding="utf-8")
        dex = DEX.read_text(encoding="utf-8")
        analytics = ANALYTICS.read_text(encoding="utf-8")
        probe = PROBE.read_text(encoding="utf-8")
        runbook = RUNBOOK.read_text(encoding="utf-8")
        kustomization = KUSTOMIZATION.read_text(encoding="utf-8")

        if contract.get("contract_version") != "belacca.native-network-policy.v1":
            fail("unexpected native network-policy contract version")
        if contract.get("environment") != "native-production":
            fail("network-policy contract must identify native production")
        if contract.get("service_cidr") != "10.43.0.0/16":
            fail("network-policy contract must record the native service CIDR")
        if not all(item.get("id") in probe for item in contract.get("required_edges", [])):
            fail("live probe is missing a required edge ID")
        if not all(item.get("id") in probe for item in contract.get("forbidden_edges", [])):
            fail("live probe is missing a forbidden edge ID")
        probe_contract = contract.get("probe", {})
        if probe_contract.get("requires_live_evidence") is not True:
            fail("network-policy probe must require live evidence")
        if probe_contract.get("ttl_seconds") != 300:
            fail("diagnostic workloads must be short-lived")

        required_ids = {item.get("id") for item in contract.get("required_edges", [])}
        expected_required = {
            "traefik-gateway", "gateway-static", "gateway-api", "api-room",
            "room-callback", "api-kubernetes-api", "pong-dns", "prometheus-pong",
            "prometheus-flux", "analytics-dex", "analytics-upstream", "headlamp-dex", "headlamp-upstream",
            "longhorn-storage",
        }
        if required_ids != expected_required:
            fail(f"required edge IDs are {sorted(required_ids)}, expected {sorted(expected_required)}")
        forbidden_ids = {item.get("id") for item in contract.get("forbidden_edges", [])}
        expected_forbidden = {
            "diagnostic-to-pong-api", "diagnostic-to-room", "diagnostic-to-dex",
            "diagnostic-to-flux", "diagnostic-to-longhorn",
        }
        if forbidden_ids != expected_forbidden:
            fail("forbidden edge IDs do not cover every protected boundary")

        require(
            bundle,
            (
                "name: native-pong-default-deny",
                "name: native-pong-gateway-ingress",
                "name: native-pong-static-ingress",
                "name: native-pong-api-traffic",
                "name: native-pong-room-traffic",
                "component: gateway",
                "component: static",
                "component: api",
                "role: room",
                "k8s-app: kube-dns",
                "cidr: 10.43.0.1/32",
                "app: source-controller",
                "app: kustomize-controller",
                "app: helm-controller",
                "app: notification-controller",
                "name: native-platform-control-plane-deny",
                "name: native-headlamp-default-deny",
                "name: native-headlamp-auth-ingress",
                "name: native-headlamp-backend-ingress",
                "cidr: 10.42.0.1/32",
                "cidr: 10.42.1.1/32",
                "cidr: 10.42.2.1/32",
            ),
            "native policy bundle",
        )
        if "0.0.0.0/0" in bundle or "10.42.0.0/16" in bundle:
            fail("native policy bundle contains a broad cluster CIDR")
        if re.search(r"(?:from|to):\s*\n\s*-\s*(?:namespaceSelector|podSelector):\s*\{\}", bundle):
            fail("native policy bundle contains a broad namespace/pod allow")

        require(longhorn, ("networkPolicies:", "enabled: true", "type: k3s"), "Longhorn HelmRelease")
        require(
            platform,
            (
                "name: native-policies",
                "path: ./clusters/belacca-production/policies",
                "- name: pong",
                "- name: native-observability",
                "- name: native-dex",
                "- name: native-analytics",
                "- name: native-headlamp",
            ),
            "native policy Flux wiring",
        )
        require(kustomization, ("network-policies.yaml", "edge-contract.json"), "policy Kustomization")
        require(
            probe,
            (
                "CNI_IDENTITY:?",
                "DIAGNOSTIC_IMAGE:?",
                'CONTEXT="${KUBE_CONTEXT:-belacca-native}"',
                'ROOM_SERVICE="${ROOM_SERVICE:-}"',
                "kubernetes.default=$api_ip expected=10.43.0.1",
                "CNI enforcement demonstrated",
                "forbidden_probe",
                "longhorn-manager",
                "kubectl -n longhorn-system get networkpolicy longhorn-manager",
                "headlamp-upstream",
                "kubectl -n pong delete pod np-gateway-source np-api-source np-room-source",
            ),
            "live policy probe",
        )
        if re.search(r"kubectl\s+-n\s+(?:pong|dex|analytics|flux-system)\s+delete\s+(?:namespace|pvc)", probe):
            fail("live policy probe contains a destructive namespace/PVC delete")
        if not re.search(r"DIAGNOSTIC_IMAGE.*approved image pinned by digest", probe):
            fail("live policy probe must require a digest-pinned diagnostic image")

        # Cross-node host-network forwarding on native flannel-wireguard is
        # evaluated from the node CNI gateways. Only the observed /32s are
        # valid; a Pod CIDR or any other broad exception bypasses identity.
        allowed_cni_gateways = {
            "cidr: 10.42.0.1/32",
            "cidr: 10.42.1.1/32",
            "cidr: 10.42.2.1/32",
        }
        for path in NATIVE_NETWORK_POLICIES:
            text = path.read_text(encoding="utf-8")
            for match in re.findall(r"cidr:\s*10\.42\.[^\s]+", text):
                if f"cidr: {match.split(':', 1)[1].strip()}" not in allowed_cni_gateways:
                    fail(f"{path} contains an unreviewed Pod/CNI CIDR exception: {match}")
        for path, text in ((DEX, dex), (ANALYTICS, analytics)):
            for match in re.findall(r"cidr:\s*10\.42\.[^\s]+", text):
                if f"cidr: {match.split(':', 1)[1].strip()}" not in allowed_cni_gateways:
                    fail(f"{path} contains an unreviewed Pod/CNI CIDR exception: {match}")

        require(
            runbook,
            (
                "## Enforcement gate",
                "required_edges",
                "forbidden_edges",
                "CNI identity",
                "Rollback",
                "game day",
                "Longhorn",
                "Flux",
                "identity",
                "analytics",
                "callback",
            ),
            "native policy runbook",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"network-policy validation failed: {error}", file=sys.stderr)
        return 1
    print("validated native NetworkPolicy contract and fail-closed probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
