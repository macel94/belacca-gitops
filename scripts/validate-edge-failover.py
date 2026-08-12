#!/usr/bin/env python3
"""Validate the native API and public-edge failover contract and evidence."""

from __future__ import annotations

import json
import ipaddress
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "clusters" / "belacca-production" / "edge" / "failover-contract.json"
EVIDENCE_PATH = ROOT / "docs" / "evidence" / "api-edge-failover.json"

PUBLIC_PORTS = {80, 443, 6443}
FORBIDDEN_PORTS = {2379, 2380, 8472, 9500, 9501, 9502, 9503, 10250, 9090}
REQUIRED_SCENARIOS = {"one-edge-failure", "one-control-plane-failure"}
REQUIRED_MEASUREMENTS = {
    "failureToWithdrawSeconds",
    "recoveryToReaddSeconds",
    "clientConvergenceObservationSeconds",
}


def fail(message: str) -> None:
    raise ValueError(message)


def string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")
    return value


def integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        fail(f"{field} must be an integer")
    return value


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("apiVersion") != "belacca.com/v1alpha1":
        fail("failover contract has an unexpected apiVersion")
    if contract.get("kind") != "EdgeFailoverContract":
        fail("failover contract has an unexpected kind")
    metadata = contract.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("cluster") != "belacca-native":
        fail("failover contract must identify belacca-native")
    if contract.get("provider", {}).get("name") != "Contabo":
        fail("provider selection must remain Contabo")
    provider = contract["provider"]
    if provider.get("selection") != "provider-managed-L4-load-balancer":
        fail("provider selection must be a managed L4 load balancer")
    if provider.get("selectionStatus") != "selected-design-not-provisioned":
        fail("provider status must remain fail-closed until provisioned")
    if provider.get("tlsTermination") != "backend-pass-through":
        fail("the provider must not terminate backend TLS")
    if provider.get("singleActiveFrontend") is not True:
        fail("the design must have one active frontend")

    endpoints = contract.get("endpoints", {})
    api = endpoints.get("api", {})
    if api.get("hostname") != "k3s-api.belacca.com":
        fail("API endpoint must be k3s-api.belacca.com")
    if api.get("listenerPort") != 6443 or api.get("kubeconfigServer") != "https://k3s-api.belacca.com:6443":
        fail("API listener and kubeconfig endpoint are not aligned")
    if api.get("certificateSAN") != api.get("hostname"):
        fail("API certificate SAN must match the stable API hostname")
    if api.get("dnsModeAfterProvisioning") != "single-dns-only-A-to-provider-vip":
        fail("API DNS must converge to one provider VIP after provisioning")

    ingress = endpoints.get("publicIngress", {})
    if set(ingress.get("listenerPorts", [])) != {80, 443}:
        fail("public ingress must expose exactly ports 80 and 443")
    if ingress.get("dnsModeAfterProvisioning") != "single-dns-only-A-to-provider-vip":
        fail("public DNS must converge to one provider VIP after provisioning")
    if ingress.get("tlsTerminationOwner") != "native-traefik":
        fail("public TLS must remain owned by native Traefik")

    backends = contract.get("backends", {})
    nodes = backends.get("controlPlane")
    if backends.get("mode") != "active-active" or not isinstance(nodes, list) or len(nodes) != 3:
        fail("the contract must contain three active-active control-plane backends")
    addresses = set()
    for index, node in enumerate(nodes):
        prefix = f"backends.controlPlane[{index}]"
        string(node.get("name"), f"{prefix}.name")
        address = string(node.get("address"), f"{prefix}.address")
        try:
            ipaddress.ip_address(address)
        except ValueError:
            fail(f"{prefix}.address is not an IP address")
        addresses.add(address)
        if node.get("apiPort") != 6443 or set(node.get("ingressPorts", [])) != {80, 443}:
            fail(f"{prefix} has an unsafe or incomplete listener set")
    if len(addresses) != 3:
        fail("control-plane backend addresses must be unique")

    checks = contract.get("healthChecks", {})
    api_check = checks.get("api", {})
    if api_check.get("path") != "/readyz" or api_check.get("expectedStatus") != 200:
        fail("API health check must require HTTP 200 from /readyz")
    if api_check.get("host") != api["hostname"] or api_check.get("sni") != api["hostname"]:
        fail("API health check SNI/Host must use the stable API hostname")
    edge_check = checks.get("edge", {})
    if edge_check.get("path") != "/health" or edge_check.get("expectedStatus") != 200:
        fail("edge health check must require HTTP 200 from /health")
    for name in ("api", "edge"):
        check = checks[name]
        for field in ("intervalSeconds", "timeoutSeconds", "unhealthyAfterFailures", "healthyAfterSuccesses"):
            if integer(check.get(field), f"healthChecks.{name}.{field}") <= 0:
                fail(f"healthChecks.{name}.{field} must be positive")
        if check["timeoutSeconds"] >= check["intervalSeconds"]:
            fail(f"healthChecks.{name} timeout must be shorter than interval")

    boundary = contract.get("networkBoundary", {})
    if set(boundary.get("publicListenerPorts", [])) != PUBLIC_PORTS:
        fail("public listener port set must be exactly 80/443/6443")
    if set(boundary.get("backendPorts", [])) != PUBLIC_PORTS:
        fail("backend port set must be exactly 80/443/6443")
    if set(boundary.get("deniedPorts", [])) != FORBIDDEN_PORTS:
        fail("private infrastructure port deny-list changed")
    if any(port in PUBLIC_PORTS for port in boundary["deniedPorts"]):
        fail("a public listener was put on the denied-port list")

    if "keepalived" not in backends.get("fencing", "").lower():
        fail("fencing must prohibit node VIP ownership")
    ownership = contract.get("ownershipAndRecovery", {})
    for field in ("activeOwner", "passiveFallback", "withdrawal", "apiRecovery", "edgeRecovery"):
        string(ownership.get(field), f"ownershipAndRecovery.{field}")
    if ownership["activeOwner"] != "provider-managed-L4-VIP":
        fail("only the provider-managed VIP may own the active frontend")
    split_brain = ownership["splitBrainPrevention"].lower()
    if "provider vip" not in split_brain or "backend a" not in split_brain:
        fail("split-brain prevention must prohibit concurrent provider VIP and backend A records")

    evidence = contract.get("evidence", {})
    if evidence.get("status") != "pending-live-drill":
        fail("contract evidence must remain pending until a live drill exists")
    if set(evidence.get("requiredScenarios", [])) != {"one-edge-failure", "one-control-plane-failure", "recovery-of-each-failed-backend"}:
        fail("contract must require edge/control-plane failure and recovery evidence")
    if "No live provider VIP" not in evidence.get("limitation", ""):
        fail("contract must state the live validation limitation")


def validate_evidence(evidence: dict[str, Any]) -> None:
    if evidence.get("apiVersion") != "belacca.com/v1alpha1" or evidence.get("kind") != "EdgeFailoverEvidence":
        fail("evidence has an unexpected identity")
    if evidence.get("environment") != "native-production":
        fail("evidence must identify native production")
    if evidence.get("status") not in {"pending-live-drill", "complete"}:
        fail("evidence has an unsupported status")
    scenarios = evidence.get("scenarios")
    if not isinstance(scenarios, dict) or set(scenarios) != REQUIRED_SCENARIOS:
        fail("evidence must contain exactly the required failure scenarios")
    if evidence["status"] == "pending-live-drill":
        if evidence.get("providerVip") is not None or evidence.get("observedAtUtc") is not None or evidence.get("operator") is not None:
            fail("pending evidence cannot contain live provider/operator claims")
        if any(scenario.get("status") != "not-run" for scenario in scenarios.values()):
            fail("pending evidence cannot contain a completed scenario")
    else:
        if any(scenario.get("status") != "complete" for scenario in scenarios.values()):
            fail("complete evidence must contain complete edge and control-plane scenarios")
        for field in ("providerVip", "observedAtUtc", "operator"):
            string(evidence.get(field), f"evidence.{field}")
        try:
            ipaddress.ip_address(evidence["providerVip"])
        except ValueError:
            fail("evidence.providerVip must be an IP address")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T[^ ]+Z", evidence["observedAtUtc"]):
            fail("evidence.observedAtUtc must be a UTC timestamp")

    for name, scenario in scenarios.items():
        if scenario.get("status") not in {"not-run", "complete"}:
            fail(f"scenario {name} has an unsupported status")
        measurements = scenario.get("measurements", {})
        required = REQUIRED_MEASUREMENTS | ({"kubeconfigApiAvailabilityDuringFailure"} if name == "one-control-plane-failure" else set())
        if not required <= measurements.keys():
            fail(f"scenario {name} is missing required measurements")
        ports = scenario.get("portsChecked")
        if not isinstance(ports, list) or any(port not in PUBLIC_PORTS for port in ports):
            fail(f"scenario {name} includes a forbidden port check")
        if scenario.get("status") == "complete" and set(ports) != PUBLIC_PORTS:
            fail(f"complete scenario {name} must check every allowed public port")
        if scenario["status"] == "not-run":
            if scenario.get("failureInjected") is not False or any(value is not None for value in measurements.values()):
                fail(f"not-run scenario {name} contains invented measurements")
        else:
            if scenario.get("failureInjected") is not True:
                fail(f"complete scenario {name} must record an injected failure")
            for field, value in measurements.items():
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    fail(f"complete scenario {name} has invalid measurement {field}")


def main() -> int:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        if not isinstance(contract, dict) or not isinstance(evidence, dict):
            fail("contract and evidence must be JSON objects")
        validate_contract(contract)
        validate_evidence(evidence)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"edge failover validation failed: {error}", file=sys.stderr)
        return 1
    print("validated native API and public-edge failover contract/evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
