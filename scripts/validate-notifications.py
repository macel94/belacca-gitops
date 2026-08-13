#!/usr/bin/env python3
"""Validate the native Flux and Alertmanager notification routing contract."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "clusters/belacca-production/notifications.yaml"
ROUTING = ROOT / "clusters/belacca-production/notification-routing.json"
ALERTMANAGER = ROOT / "clusters/belacca-production/observability/alertmanager-config.yaml"
ALERTMANAGER_DEPLOYMENT = ROOT / "clusters/belacca-production/observability/alertmanager-deployment.yaml"
ROOT_KUSTOMIZE = ROOT / "clusters/belacca-production/kustomization.yaml"
DOCS = ROOT / "docs/NOTIFICATIONS.md"


def fail(message: str) -> None:
    raise ValueError(message)


def split_documents(text: str) -> list[str]:
    return [
        part
        for part in re.split(r"(?m)^---\s*$", text)
        if re.search(r"(?m)^apiVersion:", part)
    ]


def validate_flux_contract() -> None:
    text = NATIVE.read_text(encoding="utf-8")
    docs = split_documents(text)
    if len(docs) != 6:
        fail(f"native notification manifest must contain exactly six resources, got {len(docs)}")
    for marker in (
        "platform-webhook",
        "platform-page-webhook",
        "native-production",
        "belacca-native",
        "notification-class: diagnostic",
    ):
        if marker not in text:
            fail(f"missing notification marker: {marker}")
    if "type: alertmanager" not in text:
        fail("Flux notifications must use the central Alertmanager receiver")
    if "alertmanager-native.observability.svc.cluster.local:9093/api/v2/alerts/" not in text:
        fail("Flux notifications must target the in-cluster Alertmanager API")
    if "notifications.yaml" not in ROOT_KUSTOMIZE.read_text(encoding="utf-8"):
        fail("native root does not wire notifications")
    if re.search(r"(?im)^\s*(?:token|password|authorization|apiKey):", text):
        fail("notification manifest contains credential values")
    for address in re.findall(r"(?im)^\s*address:\s*(\S+)", text):
        if not address.startswith("http://alertmanager-native.observability.svc.cluster.local:9093/"):
            fail("notification manifest contains an external endpoint")
    for alert_name, notification_class in (
        ("platform-deployments", "diagnostic"),
        ("platform-page-recovery", "page-recovery"),
    ):
        alert = re.search(
            rf"(?ms)^  name: {re.escape(alert_name)}$.*?(?=^---|\Z)",
            text,
        )
        if not alert or f"notificationClass: {notification_class}" not in alert.group(0):
            fail(f"notification manifest is missing the {alert_name} Alert")
        if "exclusionList:\n    - '.*Dependencies do not meet ready condition.*'" not in alert.group(0):
            fail(f"{alert_name} must exclude dependency-not-ready events")


def embedded_alertmanager_config() -> str:
    """Return the indented Alertmanager YAML from its ConfigMap as plain text."""
    lines = ALERTMANAGER.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("  alertmanager.yml: |") + 1
    except ValueError:
        fail("Alertmanager ConfigMap must contain data.alertmanager.yml")
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("    "):
            body.append(line[4:])
        elif not line.strip():
            body.append("")
        else:
            break
    if not body or not any(line.strip() for line in body):
        fail("embedded Alertmanager configuration is empty")
    return "\n".join(body) + "\n"


def receiver_block(config: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  - name: {re.escape(name)}\n(?P<body>.*?)(?=^  - name:|\Z)",
        config,
    )
    if not match:
        fail(f"Alertmanager receiver {name} is missing")
    return match.group("body")


def validate_alertmanager_contract() -> None:
    config = embedded_alertmanager_config()
    expected = {
        "telegram-diagnostic": ("false", "/etc/alertmanager/secrets/bot-token", "/etc/alertmanager/secrets/chat-id"),
        "telegram-page": ("true", "/etc/alertmanager/secrets/bot-token", "/etc/alertmanager/secrets/chat-id"),
    }
    if not re.search(
        r"(?ms)^route:\n(?:(?!^inhibit_rules:).)*?^  receiver: telegram-diagnostic\s*$",
        config,
    ):
        fail("Alertmanager default route must use telegram-diagnostic")
    receiver_names = re.findall(r"(?m)^  - name: ([^\s]+)\s*$", config)
    if receiver_names != list(expected):
        fail("Alertmanager must define exactly the diagnostic and page Telegram receivers")
    for name, (send_resolved, bot_token_file, chat_id_file) in expected.items():
        block = receiver_block(config, name)
        if len(re.findall(r"(?m)^    telegram_configs:\s*$", block)) != 1:
            fail(f"{name} must define exactly one telegram_configs integration")
        if not re.search(rf"(?m)^        send_resolved: {send_resolved}\s*$", block):
            fail(f"{name} must explicitly set send_resolved={send_resolved}")
        if not re.search(rf"(?m)^      - bot_token_file: {re.escape(bot_token_file)}\s*$", block):
            fail(f"{name} must use the mounted bot-token file")
        if not re.search(rf"(?m)^        chat_id_file: {re.escape(chat_id_file)}\s*$", block):
            fail(f"{name} must use the mounted chat-id file")

    required_routes = {
        ("telegram-diagnostic", 'notificationClass="diagnostic"'),
        ("telegram-diagnostic", 'notification_class="diagnostic"'),
        ("telegram-page", 'notificationClass="page"'),
        ("telegram-page", 'notification_class="page"'),
        ("telegram-page", 'notificationClass="page-recovery"'),
        ("telegram-page", 'notification_class="page-recovery"'),
    }
    route_body = re.search(r"(?ms)^route:\n(?P<body>.*?)(?=^inhibit_rules:)", config)
    if not route_body:
        fail("Alertmanager route block is missing")
    actual_routes = set()
    for child in re.finditer(
        r"(?ms)^    - receiver: (?P<receiver>[^\s]+)\n(?P<body>.*?)(?=^    - receiver:|\Z)",
        route_body.group("body"),
    ):
        actual_routes.update(
            (child.group("receiver"), matcher)
            for matcher in re.findall(r"(?m)^        - (.+)$", child.group("body"))
        )
    if not required_routes <= actual_routes:
        fail(f"Alertmanager route contract is missing {sorted(required_routes - actual_routes)}")
    if not re.search(
        r"(?m)^  group_by: \[cluster, alertname, service, namespace, name\]\s*$",
        config,
    ):
        fail("Alertmanager grouping identity changed unexpectedly")
    if len(re.findall(r"(?m)^  - source_matchers:\s*$", config)) != 3:
        fail("Alertmanager inhibition contract changed unexpectedly")


def validate_restart_contract() -> None:
    deployment = ALERTMANAGER_DEPLOYMENT.read_text(encoding="utf-8")
    if not re.search(r"(?m)^  strategy:\n    type: Recreate\s*$", deployment):
        fail("Alertmanager must use Recreate for its ReadWriteOnce data PVC")
    expected_checksum = hashlib.sha256(ALERTMANAGER.read_bytes()).hexdigest()
    match = re.search(r"(?m)^        checksum/config: ([0-9a-f]{64})\s*$", deployment)
    if not match:
        fail("Alertmanager pod template must contain a SHA-256 config checksum")
    if match.group(1) != expected_checksum:
        fail("Alertmanager pod template config checksum is stale")


def validate_json_consistency() -> None:
    routing = json.loads(ROUTING.read_text(encoding="utf-8"))
    lanes = {lane.get("name"): lane for lane in routing.get("lanes", [])}
    expected_lanes = {
        "ticket-dashboard": ("telegram-diagnostic", False),
        "page": ("telegram-page", True),
        "page-recovery": ("telegram-page", True),
    }
    for lane_name, (receiver, send_resolved) in expected_lanes.items():
        lane = lanes.get(lane_name)
        if not lane or lane.get("receiver") != receiver or lane.get("send_resolved") is not send_resolved:
            fail(f"notification-routing.json lane {lane_name} disagrees with Alertmanager")
    receivers = routing.get("policy", {}).get("telegram_receivers", {})
    if receivers.get("telegram-diagnostic", {}).get("send_resolved") is not False:
        fail("notification-routing.json diagnostic receiver must suppress resolved delivery")
    if receivers.get("telegram-page", {}).get("send_resolved") is not True:
        fail("notification-routing.json page receiver must retain resolved delivery")
    if routing.get("policy", {}).get("default_receiver") != "telegram-diagnostic":
        fail("notification-routing.json default receiver must be diagnostic")


def validate_docs() -> None:
    docs = " ".join(DOCS.read_text(encoding="utf-8").split()).lower()
    for marker in (
        "separate diagnostic/default and actionable page",
        "telegram-diagnostic",
        "telegram-page",
        "dependencies do not meet ready condition",
        "diagnostic health-check recoveries are deliberately suppressed",
        "actionable page",
        "send_resolved",
        "recreate",
        "checksum/config",
        "restore or tune",
        "verification",
        "out of band",
        "external monitoring is intentionally deferred",
    ):
        if " ".join(marker.lower().split()) not in docs:
            fail(f"notification docs missing {marker}")


def main() -> int:
    try:
        validate_flux_contract()
        validate_alertmanager_contract()
        validate_restart_contract()
        validate_json_consistency()
        validate_docs()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"notification validation failed: {exc}", file=sys.stderr)
        return 1
    print("validated native Flux, Alertmanager, and Telegram notification routing contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
