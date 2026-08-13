#!/usr/bin/env python3
"""Fail-closed native-production game-day safety gate.

The default operation is read-only preflight. This helper intentionally supports
only exact-name Pod restarts; host power operations, Longhorn fault injection,
DNS changes, Git pushes, and external synthetic runs remain owner-operated.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, NoReturn

EXPECTED_CONTEXT = "belacca-native"
NATIVE_NODES = {"belacca-k3s-01", "belacca-k3s-02", "belacca-k3s-03"}
PROTECTED_PVCS = {
    ("pong", "pong-api-data"),
    ("analytics", "goatcounter-data"),
    ("dex", "dex-data"),
    ("observability", "prometheus-native-data"),
}
POD_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def fail(message: str) -> NoReturn:
    raise SafetyError(message)


class SafetyError(RuntimeError):
    """A precondition or scope check failed; no mutation was attempted."""


def invoke(
    args: list[str], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> str:
    """Run a command without a shell and return stdout; never expose stderr."""
    try:
        result = runner(
            args,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        # Do not echo command stderr: kubectl/plugin diagnostics can contain
        # private endpoints or operator-supplied values.
        fail(f"command failed ({' '.join(args[:3])}…)")
    return result.stdout


def kubectl(*args: str, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> str:
    return invoke(["kubectl", *args], runner=runner)


def require_native_context(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    context = kubectl("config", "current-context", runner=runner).strip()
    if context != EXPECTED_CONTEXT:
        fail(f"wrong Kubernetes context {context!r}; expected {EXPECTED_CONTEXT!r}")


def require_gate(args: argparse.Namespace) -> None:
    if not args.execute:
        fail("dry-run only; pass --execute for a mutation")
    if args.ack_issue != 4:
        fail("mutation requires --ack-issue 4")
    if not args.confirm_production:
        fail("mutation requires --confirm-production")


def valid_exact_name(value: str, label: str) -> str:
    if not POD_NAME.fullmatch(value) or len(value) > 253:
        fail(f"{label} must be one exact DNS-compatible resource name")
    return value


def parse_json(output: str, description: str) -> dict[str, Any]:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        fail(f"{description} was not JSON: {error}")
    if not isinstance(value, dict):
        fail(f"{description} was not a JSON object")
    return value


def pod_ready(pod: dict[str, Any]) -> bool:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    return bool(statuses) and all(item.get("ready") is True for item in statuses)


def get_pod(
    namespace: str,
    name: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    valid_exact_name(name, "pod")
    return parse_json(kubectl("-n", namespace, "get", "pod", name, "-o", "json", runner=runner), "pod")


def node_name(pod: dict[str, Any]) -> str:
    value = pod.get("spec", {}).get("nodeName")
    if not isinstance(value, str) or value not in NATIVE_NODES:
        fail("target Pod is not scheduled on a named native production server")
    return value


def ensure_traefik_target(
    pod: dict[str, Any], expected_node: str, runner: Callable[..., subprocess.CompletedProcess[str]]
) -> None:
    if expected_node not in NATIVE_NODES:
        fail(f"unknown native node {expected_node!r}")
    if node_name(pod) != expected_node:
        fail("target Traefik Pod is not on the explicitly supplied node")
    labels = pod.get("metadata", {}).get("labels", {})
    if labels.get("app.kubernetes.io/name") != "traefik":
        fail("target Pod is not a Traefik Pod")
    if not pod_ready(pod):
        fail("target Traefik Pod is not Ready")
    peers = parse_json(
        kubectl(
            "-n", "kube-system", "get", "pods",
            "-l", "app.kubernetes.io/name=traefik", "-o", "json", runner=runner
        ),
        "Traefik peer list",
    ).get("items", [])
    ready_peers = [item for item in peers if pod_ready(item)]
    if len(ready_peers) < 3:
        fail("edge drill requires all three native Traefik Pods Ready before deletion")


def ensure_pong_target(
    pod: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]]
) -> None:
    metadata = pod.get("metadata", {})
    labels = metadata.get("labels", {})
    if labels.get("component") != "api" or labels.get("app") != "cloudnativepong":
        fail("target Pod is not the native cloudnativepong API")
    if not pod_ready(pod):
        fail("target Pong API Pod is not Ready")
    claims = [
        volume.get("persistentVolumeClaim", {}).get("claimName")
        for volume in pod.get("spec", {}).get("volumes", [])
        if "persistentVolumeClaim" in volume
    ]
    if claims != ["pong-api-data"]:
        fail("Pong API target does not mount exactly the protected pong-api-data claim")
    if ("pong", "pong-api-data") in PROTECTED_PVCS:
        # This is an intentional explicit guard: the PVC may be observed, never mutated.
        pass
    owners = metadata.get("ownerReferences", [])
    if not any(owner.get("kind") == "ReplicaSet" for owner in owners):
        fail("Pong API target is not Deployment-managed")
    peers = parse_json(
        kubectl(
            "-n", "pong", "get", "pods", "-l", "app=cloudnativepong,component=api",
            "-o", "json", runner=runner
        ),
        "Pong API peer list",
    ).get("items", [])
    if sum(pod_ready(item) for item in peers) != 1:
        fail("Pong API drill requires exactly one Ready API writer")


def delete_exact_pod(
    namespace: str,
    name: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    valid_exact_name(name, "pod")
    if name in {pvc for _, pvc in PROTECTED_PVCS}:
        fail("refusing a protected PVC name in any namespace")
    kubectl("-n", namespace, "delete", "pod", name, "--wait=false", runner=runner)


def restart_traefik(args: argparse.Namespace, runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    require_gate(args)
    require_native_context(runner)
    valid_exact_name(args.pod, "pod")
    pod = get_pod("kube-system", args.pod, runner)
    ensure_traefik_target(pod, args.node, runner)
    delete_exact_pod("kube-system", args.pod, runner)
    print(f"deleted exact Traefik Pod {args.pod!r}; monitor its replacement")


def restart_pong(args: argparse.Namespace, runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    require_gate(args)
    require_native_context(runner)
    valid_exact_name(args.pod, "pod")
    pod = get_pod("pong", args.pod, runner)
    ensure_pong_target(pod, runner)
    delete_exact_pod("pong", args.pod, runner)
    print(f"deleted exact Pong API Pod {args.pod!r}; monitor its replacement and PVC")


def preflight(args: argparse.Namespace, runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    require_native_context(runner)
    checks: dict[str, str] = {"context": EXPECTED_CONTEXT}
    nodes = parse_json(kubectl("get", "nodes", "-o", "json", runner=runner), "node list")
    observed = {
        item.get("metadata", {}).get("name"): item
        for item in nodes.get("items", [])
        if item.get("metadata", {}).get("name") in NATIVE_NODES
    }
    missing = sorted(NATIVE_NODES - set(observed))
    if missing:
        fail(f"native server inventory is missing {', '.join(missing)}")
    not_ready = sorted(
        name for name, item in observed.items()
        if not any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in item.get("status", {}).get("conditions", [])
        )
    )
    if not_ready:
        fail(f"native server inventory is not Ready: {', '.join(not_ready)}")
    checks["native_nodes"] = "present-and-ready"
    for namespace, pvc in sorted(PROTECTED_PVCS):
        value = kubectl("-n", namespace, "get", "pvc", pvc, "-o", "json", runner=runner)
        claim = parse_json(value, f"protected PVC {namespace}/{pvc}")
        if claim.get("metadata", {}).get("name") != pvc:
            fail(f"protected PVC identity mismatch for {namespace}/{pvc}")
    checks["protected_pvcs"] = "observed-without-mutation"
    # These commands are intentionally status-only and do not print their output.
    kubectl("get", "--raw", "/readyz?verbose", runner=runner)
    kubectl("-n", "flux-system", "get", "kustomizations", "-o", "json", runner=runner)
    kubectl("-n", "kube-system", "get", "daemonset", "traefik", "-o", "json", runner=runner)
    kubectl("-n", "longhorn-system", "get", "nodes", "-o", "json", runner=runner)
    checks["api_flux_traefik_longhorn"] = "read-only probes passed"
    result = {"schema_version": "1.0", "environment": "native-production", "checks": checks}
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        Path(args.evidence).write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--execute", action="store_true")
    common.add_argument("--ack-issue", type=int, default=None)
    common.add_argument("--confirm-production", action="store_true")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("preflight", parents=[common])
    check.add_argument("--evidence")
    edge = sub.add_parser("restart-traefik-pod", parents=[common])
    edge.add_argument("--pod", required=True)
    edge.add_argument("--node", required=True)
    pong = sub.add_parser("restart-pong-api-pod", parents=[common])
    pong.add_argument("--pod", required=True)
    return parser


def main(
    argv: list[str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "preflight":
            preflight(args, runner)
        elif args.command == "restart-traefik-pod":
            restart_traefik(args, runner)
        elif args.command == "restart-pong-api-pod":
            restart_pong(args, runner)
        else:
            fail(f"unsupported command {args.command!r}")
    except SafetyError as error:
        print(f"FAIL CLOSED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
