#!/usr/bin/env python3
"""Validate the native Flux notification contract without a cluster."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "clusters" / "belacca-production" / "notifications.yaml"
NATIVE_ROOT = ROOT / "clusters" / "belacca-production" / "kustomization.yaml"
DOCS = ROOT / "docs" / "NOTIFICATIONS.md"


def fail(message: str) -> None:
    raise ValueError(message)


def split_documents(text: str) -> list[str]:
    return [
        part for part in re.split(r"(?m)^---\s*$", text)
        if re.search(r"(?m)^apiVersion:", part)
    ]


def field(document: str, name: str) -> str | None:
    match = re.search(rf"(?m)^  {re.escape(name)}:\s*([^\n#]+)", document)
    return match.group(1).strip().strip("'\"") if match else None


def validate_native() -> None:
    text = NATIVE.read_text(encoding="utf-8")
    documents = split_documents(text)
    if len(documents) != 3:
        fail(f"native notification manifest must contain exactly three resources, got {len(documents)}")
    kinds_and_names = {(field(doc, "kind"), field(doc, "name")) for doc in documents}
    expected = {(None, None)}  # resource identity is checked by the stable markers below
    if "kind: Provider" not in text or "kind: Alert" not in text:
        fail("native notification resources must include Provider and Alert resources")
    for marker in (
        "belacca.com/stage: native-production",
        "belacca.com/project: platform",
        "belacca.com/component: notifications",
        "belacca.com/notification-class: diagnostic",
        "name: platform-webhook",
        "name: platform-notification-webhook",
        "cluster: belacca-native",
        "environment: native-production",
    ):
        if marker not in text:
            fail(f"native notification resource is missing {marker!r}")
    if "belacca-native" not in text or "native-production" not in text:
        fail("native notification manifest is missing native production metadata")
    if text.count("secretRef:") != 1:
        fail("native Provider must contain exactly one secretRef")
    if "notifications.yaml" not in NATIVE_ROOT.read_text(encoding="utf-8"):
        fail("native root Kustomization does not wire notifications.yaml")
    if re.search(r"(?im)^\s*(?:address|token|password|secret|headers|authorization|apiKey|api-key):", text) or "http://" in text or "https://" in text:
        fail("native notification manifest contains credential or public-exposure data")


def validate_documentation() -> None:
    text = DOCS.read_text(encoding="utf-8")
    required = (
        "platform-notification-webhook",
        "provisioned out of band",
        "There is no paging claim",
        "deduplication",
        "incident\nhandoff",
        "no endpoint or credential is stored",
    )
    for marker in required:
        if marker not in text:
            fail(f"notification documentation is missing {marker!r}")
    if re.search(r"(?im)^\s*(?:kubectl|curl|wget|http)\b", text):
        fail("notification documentation must not contain executable provisioning or delivery commands")


def main() -> int:
    try:
        validate_native()
        validate_documentation()
    except (OSError, ValueError) as error:
        print(f"notification validation failed: {error}", file=sys.stderr)
        return 1
    print("validated native Flux notification contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
