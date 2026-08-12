#!/usr/bin/env python3
"""Validate historical and native Flux notification contracts without a cluster."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "clusters" / "vmi3474918" / "notifications.yaml"
NATIVE = ROOT / "clusters" / "belacca-production" / "notifications.yaml"
NATIVE_ROOT = ROOT / "clusters" / "belacca-production" / "kustomization.yaml"
DOCS = ROOT / "docs" / "NOTIFICATIONS.md"

KINDS = {"GitRepository", "Kustomization", "HelmRelease"}
NATIVE_HELM_NAMESPACES = {
    "analytics",
    "cert-manager",
    "dex",
    "flux-system",
    "headlamp",
    "kube-system",
    "longhorn-system",
    "kyverno",
}
NATIVE_SOURCES = {
    ("GitRepository", "flux-system"),
    ("Kustomization", "flux-system"),
    *{("HelmRelease", namespace) for namespace in NATIVE_HELM_NAMESPACES},
}
SOURCE = re.compile(
    r"(?m)^    - kind: (?P<kind>[A-Za-z]+)\n"
    r"^      name: ['\"]?\*['\"]?\n"
    r"^      namespace: (?P<namespace>[a-z0-9-]+)$"
)
DOCUMENT = re.compile(r"(?ms)(?:^|\n)---\s*\n(?P<body>.*?)(?=\n---\s*\n|\Z)")


def fail(message: str) -> None:
    raise ValueError(message)


def field(document: str, section: str, name: str) -> str | None:
    """Return a simple scalar field under a two-space YAML section."""
    match = re.search(
        rf"(?ms)^  {re.escape(section)}:\s*\n(?P<body>.*?)(?=^\S|\Z)",
        document,
    )
    if not match:
        return None
    value = re.search(rf"(?m)^    {re.escape(name)}:\s*([^\n#]+)", match.group("body"))
    return value.group(1).strip().strip("'\"") if value else None


def document_kind(document: str) -> str | None:
    match = re.search(r"(?m)^kind:\s*([^\n#]+)", document)
    return match.group(1).strip() if match else None


def document_name(document: str) -> str | None:
    match = re.search(r"(?m)^  name:\s*([^\n#]+)", document)
    return match.group(1).strip().strip("'\"") if match else None


def document_namespace(document: str) -> str | None:
    match = re.search(r"(?m)^  namespace:\s*([^\n#]+)", document)
    return match.group(1).strip().strip("'\"") if match else None


def split_documents(text: str) -> list[str]:
    return [match.group("body") for match in DOCUMENT.finditer("\n" + text)]


def source_set(document: str) -> set[tuple[str, str]]:
    return {(match.group("kind"), match.group("namespace")) for match in SOURCE.finditer(document)}


def validate_historical() -> None:
    text = HISTORICAL.read_text(encoding="utf-8")
    required = (
        "apiVersion: notification.toolkit.fluxcd.io/v1beta3",
        "kind: Provider",
        "name: platform-webhook",
        "name: platform-notification-webhook",
        "kind: Alert",
        "name: platform-errors",
        "name: platform-deployments",
        "eventSeverity: error",
        "eventSeverity: info",
        "cluster: k3d-pong",
        "environment: production",
        "namespace: flux-system",
        "namespace: headlamp",
        "namespace: analytics",
        "namespace: dex",
        "- '.*succeeded.*'",
        "- '.*ready.*'",
    )
    for marker in required:
        if marker not in text:
            fail(f"historical notification manifest is missing {marker!r}")
    if "belacca-native" in text or "native-production" in text:
        fail("historical notification manifest was changed to native metadata")


def validate_native() -> None:
    text = NATIVE.read_text(encoding="utf-8")
    documents = split_documents(text)
    if len(documents) != 3:
        fail(f"native notification manifest must contain exactly three resources, got {len(documents)}")

    kinds_and_names = {(document_kind(doc), document_name(doc)) for doc in documents}
    expected = {
        ("Provider", "platform-webhook"),
        ("Alert", "platform-errors"),
        ("Alert", "platform-deployments"),
    }
    if kinds_and_names != expected:
        fail(f"native notification resources must be {sorted(expected)}, got {sorted(kinds_and_names)}")

    for document in documents:
        if not document.startswith("apiVersion: notification.toolkit.fluxcd.io/v1beta3"):
            fail("native notification resources must use notification.toolkit.fluxcd.io/v1beta3")
        if document_namespace(document) != "flux-system":
            fail("native notification resources must be in flux-system")
        for marker in (
            "    belacca.com/stage: native-production",
            "    belacca.com/project: platform",
            "    belacca.com/component: notifications",
            "    belacca.com/notification-class: diagnostic",
        ):
            if marker not in document:
                fail(f"native notification resource is missing metadata {marker.strip()!r}")
        if "k3d" in document.lower():
            fail("native notification manifest contains retired k3d metadata")

    provider = next(doc for doc in documents if document_name(doc) == "platform-webhook")
    if document_kind(provider) != "Provider":
        fail("platform-webhook must be a Provider")
    for marker in (
        "  type: generic",
        "  secretRef:\n    name: platform-notification-webhook",
    ):
        if marker not in provider:
            fail(f"native Provider is missing {marker!r}")
    if provider.count("secretRef:") != 1:
        fail("native Provider must contain exactly one secretRef")

    alerts = {
        document_name(doc): doc for doc in documents if document_kind(doc) == "Alert"
    }
    for name, alert in alerts.items():
        if "  providerRef:\n    name: platform-webhook" not in alert:
            fail(f"native Alert {name} must reference platform-webhook")
        if "    cluster: belacca-native" not in alert or "    environment: native-production" not in alert:
            fail(f"native Alert {name} must identify belacca-native/native-production")
        if "    notificationClass: diagnostic" not in alert or "    pagePolicy: not-configured" not in alert:
            fail(f"native Alert {name} must be diagnostic and non-page until policy exists")
        if "    belacca.com/page-policy: not-configured" not in alert:
            fail(f"native Alert {name} must declare that paging is not configured")
        if source_set(alert) != NATIVE_SOURCES:
            fail(
                f"native Alert {name} source coverage is {sorted(source_set(alert))}, "
                f"expected {sorted(NATIVE_SOURCES)}"
            )

    errors = alerts["platform-errors"]
    if "  eventSeverity: error" not in errors:
        fail("platform-errors must select error events")
    if "  inclusionList:" in errors:
        fail("platform-errors must not use a deployment inclusion list")

    deployments = alerts["platform-deployments"]
    if "  eventSeverity: info" not in deployments:
        fail("platform-deployments must select info events")
    for pattern in ("    - '.*succeeded.*'", "    - '.*ready.*'"):
        if pattern not in deployments:
            fail(f"platform-deployments is missing inclusion pattern {pattern}")

    unsafe = (
        r"(?im)^\s*(?:address|token|password|secret|headers|authorization|apiKey|api-key):",
        r"https?://",
        r"(?im)^\s*(?:data|stringData):",
        r"(?im)^\s*kind:\s*(?:Secret|Service|Ingress|HTTPRoute|Gateway)$",
        r"(?im)^\s*(?:type:\s*(?:NodePort|LoadBalancer)|host:|routes:)",
        r"(?i)xox[bap]-|Bearer\s+[A-Za-z0-9._-]+",
    )
    for pattern in unsafe:
        if re.search(pattern, text):
            fail(f"native notification manifest contains forbidden credential or public-exposure pattern: {pattern}")

    if "notifications.yaml" not in NATIVE_ROOT.read_text(encoding="utf-8"):
        fail("native root Kustomization does not wire notifications.yaml")


def validate_documentation() -> None:
    text = DOCS.read_text(encoding="utf-8")
    required = (
        "names-only platform-notification-webhook contract is committed",
        "destination Secret is **intentionally absent**",
        "There is no paging claim",
        "99% availability over 30 days; this is a policy target, not an SLA.",
        "Controlled-drill recovery P95 under six minutes",
        "deduplicate",
        "Harmless diagnostic verification",
        "Escalation and incident handoff",
        "Safe out-of-band provisioning and rotation placeholders",
        "<approved-HTTPS-notification-endpoint>",
        "There is intentionally no real command here.",
    )
    for marker in required:
        if marker not in text:
            fail(f"notification documentation is missing {marker!r}")
    if re.search(r"(?im)^\s*(?:kubectl|curl|wget|http)\b", text):
        fail("notification documentation must not contain executable provisioning or delivery commands")


def main() -> int:
    try:
        validate_historical()
        validate_native()
        validate_documentation()
    except (OSError, ValueError) as error:
        print(f"notification validation failed: {error}", file=sys.stderr)
        return 1
    print("validated historical and native Flux notification contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
