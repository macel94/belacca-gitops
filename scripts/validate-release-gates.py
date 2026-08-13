#!/usr/bin/env python3
"""Validate the progressive-delivery policy, canary boundary, and release evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "releases" / "release-policy.json"
CANARY = ROOT / "clusters" / "belacca-canary"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
CHECKS = {"portfolio-health", "portfolio-homepage", "pong-user-journey"}
FORBIDDEN_CANARY = re.compile(
    r"(?im)^(?:\s*(?:namespace|namespaceSelector):\s*(?:production|native-production|belacca-production)\b|"
    r"\s*(?:kind:\s*(?:Secret|PersistentVolumeClaim)|claimName:|secretName:|secretRef:|persistentVolumeClaim:))"
)


def fail(message: str) -> None:
    raise ValueError(message)


def nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")
    return value


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("apiVersion") != "belacca.com/v1alpha1" or policy.get("kind") != "ReleaseGatePolicy":
        fail("release policy has an unexpected apiVersion or kind")
    stages = policy.get("stages")
    if [stage.get("name") for stage in stages or []] != ["test", "canary", "full"]:
        fail("release stages must be test, canary, full in order")
    for stage in stages:
        if set(stage.get("requiredChecks", [])) != CHECKS:
            fail(f"{stage.get('name')} stage must require portfolio and Pong checks")
    gates = policy.get("gates", {})
    for gate in ("readiness", "userJourneys", "provenance", "immutability"):
        if gates.get(gate, {}).get("required") is not True:
            fail(f"{gate} gate must be required")
    safety = policy.get("canarySafety", {})
    required_safety = {
        "productionCredentials": "denied-by-validating-admission-policy",
        "persistentVolumeClaims": "denied-by-validating-admission-policy",
        "podPersistentVolumeMounts": "denied-by-validating-admission-policy",
        "serviceAccountTokenMounts": "denied-by-validating-admission-policy",
        "nativeProductionIngress": "not configured",
    }
    for field, expected in required_safety.items():
        if safety.get(field) != expected:
            fail(f"canary safety {field} must be {expected!r}")
    evidence = policy.get("evidence", {})
    required_fields = set(evidence.get("requiredFields", []))
    if not {"sourceRevisions", "imageDigests", "provenance", "fluxRevision", "checks", "outcome"} <= required_fields:
        fail("evidence policy is missing release traceability fields")


def validate_canary() -> None:
    kustomization = (CANARY / "kustomization.yaml").read_text(encoding="utf-8")
    required = (
        "namespace.yaml",
        "quota.yaml",
        "network-policy.yaml",
        "admission-policy.yaml",
    )
    for name in required:
        if name not in kustomization:
            fail(f"canary Kustomization does not include {name}")
    for path in CANARY.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN_CANARY.search(text):
            fail(f"canary manifest contains production state or a credential/PVC reference: {path}")
    namespace = (CANARY / "namespace.yaml").read_text(encoding="utf-8")
    for marker in (
        "name: belacca-canary",
        "belacca.com/release-stage: canary",
        "belacca.com/native-production-access: denied",
        "pod-security.kubernetes.io/enforce: restricted",
    ):
        if marker not in namespace:
            fail(f"canary namespace is missing {marker!r}")
    quota = (CANARY / "quota.yaml").read_text(encoding="utf-8")
    for marker in ('secrets: "0"', 'persistentvolumeclaims: "0"'):
        if marker not in quota:
            fail(f"canary quota must set {marker}")
    network = (CANARY / "network-policy.yaml").read_text(encoding="utf-8")
    for marker in (
        "name: canary-default-deny",
        "name: canary-dns-egress",
        "k8s-app: kube-dns",
    ):
        if marker not in network:
            fail(f"canary network boundary is missing {marker!r}")
    admission = (CANARY / "admission-policy.yaml").read_text(encoding="utf-8")
    for marker in (
        "failurePolicy: Fail",
        "belacca-canary-no-secrets",
        "belacca-canary-no-persistent-volumes",
        "belacca-canary-no-pod-state-or-credentials",
        "validationActions: [Deny]",
        "persistentVolumeClaim",
        "secretKeyRef",
        "automountServiceAccountToken",
    ):
        if marker not in admission:
            fail(f"canary admission boundary is missing {marker!r}")


def validate_release(release: dict[str, Any], policy: dict[str, Any]) -> None:
    validate_policy(policy)
    nonempty(release.get("releaseId"), "releaseId")
    stage = nonempty(release.get("stage"), "stage")
    if stage not in {"test", "canary", "full"}:
        fail("release stage must be test, canary, or full")
    sources = release.get("sourceRevisions")
    if not isinstance(sources, dict) or not sources:
        fail("sourceRevisions must be a non-empty object")
    for name, revision in sources.items():
        nonempty(name, "sourceRevisions key")
        if not SHA.fullmatch(revision):
            fail(f"source revision for {name} must be a 40-character lowercase commit SHA")
    images = release.get("imageDigests")
    if not isinstance(images, dict) or not images:
        fail("imageDigests must be a non-empty object")
    for image, digest in images.items():
        nonempty(image, "imageDigests key")
        if not DIGEST.fullmatch(digest):
            fail(f"image {image} is not pinned to a complete lowercase sha256 digest")
    references = release.get("imageReferences")
    if not isinstance(references, dict) or references != {image: f"{image}@{digest}" for image, digest in images.items()}:
        fail("imageReferences must contain the exact repository@sha256 identity for every image")
    provenance = release.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("verified") is not True:
        fail("promotion is blocked until provenance is verified for every exact digest")
    nonempty(provenance.get("verifier"), "provenance.verifier")
    nonempty(provenance.get("attestationType"), "provenance.attestationType")
    verified_images = provenance.get("verifiedImages")
    if not isinstance(verified_images, list) or set(verified_images) != set(images):
        fail("provenance.verifiedImages must enumerate every exact image digest")
    evidence_uri = nonempty(provenance.get("evidenceUri"), "provenance.evidenceUri")
    if evidence_uri.startswith("<") or evidence_uri.startswith("TODO"):
        fail("provenance evidenceUri must identify immutable verification evidence")
    nonempty(release.get("fluxRevision"), "fluxRevision")
    checks = release.get("checks")
    if not isinstance(checks, list) or {item.get("id") for item in checks} != CHECKS:
        fail("release evidence must contain exactly the portfolio and Pong gate checks")
    for check in checks:
        nonempty(check.get("id"), "check.id")
        nonempty(check.get("target"), f"{check.get('id')}.target")
        if not isinstance(check.get("passed"), bool):
            fail(f"{check.get('id')}.passed must be boolean")
        if not isinstance(check.get("durationMs"), int) or check["durationMs"] < 0:
            fail(f"{check.get('id')}.durationMs must be a non-negative integer")
        nonempty(check.get("evidence"), f"{check.get('id')}.evidence")
    outcome = nonempty(release.get("outcome"), "outcome")
    if outcome not in {"promoted", "blocked", "rolled-back"}:
        fail("outcome must be promoted, blocked, or rolled-back")
    passed = all(check["passed"] for check in checks)
    if outcome == "promoted" and not passed:
        fail("a promoted release must pass every user-facing check")
    if outcome in {"blocked", "rolled-back"}:
        rollback = release.get("rollback")
        if not isinstance(rollback, dict) or rollback.get("required") is not True:
            fail("blocked or rolled-back evidence must require a reviewed Git rollback")
        nonempty(rollback.get("gitChange"), "rollback.gitChange")
        nonempty(rollback.get("fluxReconciliation"), "rollback.fluxReconciliation")
    timestamps = release.get("timestamps")
    if not isinstance(timestamps, dict):
        fail("timestamps must be an object")
    for field in ("sourceCommittedAt", "productionStartedAt"):
        value = nonempty(timestamps.get(field), f"timestamps.{field}")
        if not RFC3339.fullmatch(value):
            fail(f"timestamps.{field} must be UTC RFC3339")
    for field in ("failureDetectedAt", "rollbackCompletedAt"):
        value = timestamps.get(field)
        if value is not None and not RFC3339.fullmatch(value):
            fail(f"timestamps.{field} must be UTC RFC3339 when present")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        fail(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, help="optional release evidence JSON to validate")
    args = parser.parse_args(argv)
    try:
        policy = load_json(POLICY)
        validate_policy(policy)
        validate_canary()
        if args.release:
            validate_release(load_json(args.release), policy)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"release gate validation failed: {error}", file=sys.stderr)
        return 1
    print("validated release policy, disposable canary boundary, and release evidence contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
