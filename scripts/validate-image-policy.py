#!/usr/bin/env python3
"""Validate the native production image provenance contract offline.

This is intentionally deterministic and registry-independent. Kyverno performs
runtime signature/attestation verification; this check prevents a reviewed Git
change from weakening the policy or introducing mutable first-party images.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "policy/image-policy.json"
POLICIES = ROOT / "clusters/belacca-production/policies"
NATIVE = ROOT / "clusters/belacca-production"
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}(?:$|[\"'])")
FIRST_PARTY = (
    "ghcr.io/macel94/cloudnativepong-",
    "ghcr.io/macel94/francesco-belacca-site",
)
IMAGE_LINE = re.compile(r"^\s+image:\s+([^\s#]+)", re.MULTILINE)


def fail(message: str) -> None:
    print(f"image-policy validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path}: {exc}")
    require(isinstance(value, dict), f"{path} must contain an object")
    return value


def validate_contract(contract: dict) -> None:
    require(contract.get("version") == "native-production-v1", "contract version is not native-production-v1")
    require(contract.get("enforcementPoint", "").startswith("Kyverno"), "enforcement point must be Kyverno")
    require(contract.get("digestEnforcedNamespaces") == ["pong", "portfolio", "analytics"], "digest scope must cover only first-party application namespaces")
    vulnerabilities = contract.get("vulnerabilities", {})
    require(vulnerabilities.get("maxAllowedSeverity") == "MEDIUM", "maximum allowed severity must be MEDIUM")
    require(vulnerabilities.get("blockKnownUnfixed") is True, "known-unfixed findings must block")
    require(vulnerabilities.get("requiredAttestationPolicy") == "native-production-v1", "vulnerability policy name is missing")
    attestations = contract.get("attestations", {})
    for key in ("provenancePredicate", "sbomPredicate", "vulnerabilityPredicate", "issuer", "transparencyLog"):
        require(attestations.get(key), f"attestation field {key} is missing")
    exceptions = contract.get("exceptions", {})
    require(exceptions.get("active") == [], "active exceptions must be individually reviewed and not hidden in this repository")
    require(set(exceptions.get("requiredFields", [])) == {"owner", "rationale", "scope", "expires"}, "exception fields are incomplete")


def validate_policies(contract: dict) -> None:
    files = sorted(
        path for path in POLICIES.glob("*.yaml") if path.name != "kustomization.yaml"
    )
    require(len(files) >= 4, "native image policy manifests are missing")
    text = "\n".join(path.read_text() for path in files)
    for needle in (
        "failurePolicy: Fail",
        "failureAction: Enforce",
        "mutateDigest: false",
        "verifyDigest: true",
        "type: SigstoreBundle",
        "https://slsa.dev/provenance/v1",
        "https://cyclonedx.org/bom",
        "https://belacca.com/attestations/vulnerability/v1",
        "https://token.actions.githubusercontent.com",
        "https://rekor.sigstore.dev",
        "native-production-v1",
        "knownUnfixed",
        "{{ bomFormat }}",
        "{{ policy }}",
        "{{ maxSeverity }}",
        "{{ knownUnfixed }}",
    ):
        require(needle in text, f"policy set is missing {needle}")
    require("{{ predicate.bomFormat }}" not in text, "SBOM attestation condition uses unsupported predicate prefix")
    require("{{ predicate.policy }}" not in text, "vulnerability attestation condition uses unsupported predicate prefix")
    require("{{ predicate.maxSeverity }}" not in text, "vulnerability severity condition uses unsupported predicate prefix")
    require("{{ predicate.knownUnfixed }}" not in text, "vulnerability unfixed condition uses unsupported predicate prefix")
    for prefix in FIRST_PARTY:
        require(prefix in text, f"policy set does not match first-party prefix {prefix}")
    digest_policy = (POLICIES / "production-image-digest.yaml").read_text()
    require("@sha256:" in digest_policy, "digest policy does not require sha256")
    for namespace in contract["digestEnforcedNamespaces"]:
        require(f"                - {namespace}" in digest_policy, f"digest policy does not cover {namespace}")
    for namespace in ("cert-manager", "dex", "flux-system", "headlamp", "kube-system", "longhorn-system", "observability"):
        require(f"                - {namespace}" not in digest_policy, f"digest policy unexpectedly covers vendor namespace {namespace}")


def validate_native_dependencies() -> None:
    for name in ("native-applications.yaml", "native-platform-applications.yaml"):
        text = (NATIVE / name).read_text()
        require(text.count("- name: native-image-policy") >= (2 if name == "native-applications.yaml" else 5), f"{name} does not gate every native child on native-image-policy")
    root = (NATIVE / "kustomization.yaml").read_text()
    require("- native-policy-system.yaml" in root, "native root does not include policy-system Flux graph")


def validate_image_references(text: str, source: str) -> None:
    for image in IMAGE_LINE.findall(text):
        if image.startswith(FIRST_PARTY):
            require(DIGEST.search(image) is not None, f"mutable first-party image in {source}: {image}")


def validate_production_manifests(manifest_root: Path = NATIVE) -> None:
    for path in sorted(manifest_root.rglob("*.yaml")):
        if "/flux-system/" in str(path):
            continue
        try:
            source = str(path.relative_to(ROOT))
        except ValueError:
            source = str(path)
        validate_image_references(path.read_text(), source)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest-root",
        type=Path,
        default=NATIVE,
        help="override the manifest root (used by the deterministic negative test)",
    )
    args = parser.parse_args()
    contract = load_json(CONTRACT)
    validate_contract(contract)
    validate_policies(contract)
    validate_native_dependencies()
    validate_production_manifests(args.manifest_root)
    print("validated native production image provenance, digest, vulnerability, and exception contracts")


if __name__ == "__main__":
    main()
