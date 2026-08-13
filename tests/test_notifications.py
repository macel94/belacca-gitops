#!/usr/bin/env python3
"""Regression tests for native Telegram notification routing."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-notifications.py"
spec = importlib.util.spec_from_file_location("validate_notifications", SCRIPT)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class NotificationContractTests(unittest.TestCase):
    def test_checked_in_contract_is_valid(self) -> None:
        self.assertEqual(validator.main(), 0)

    def test_diagnostic_receiver_suppresses_resolved_delivery(self) -> None:
        config = validator.embedded_alertmanager_config()
        diagnostic = validator.receiver_block(config, "telegram-diagnostic")
        self.assertIn("send_resolved: false", diagnostic)
        self.assertNotIn("send_resolved: true", diagnostic)

    def test_page_recovery_routes_to_resolved_page_receiver(self) -> None:
        config = validator.embedded_alertmanager_config()
        self.assertIn(
            'telegram-page',
            config,
        )
        self.assertIn(
            'notificationClass="page-recovery"',
            config,
        )
        self.assertIn(
            'notification_class="page-recovery"',
            config,
        )
        self.assertIn("send_resolved: true", validator.receiver_block(config, "telegram-page"))

    def test_validator_rejects_diagnostic_resolved_delivery(self) -> None:
        original = validator.ALERTMANAGER
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "alertmanager-config.yaml"
                text = original.read_text(encoding="utf-8")
                first_false = text.index("send_resolved: false")
                text = text[:first_false] + text[first_false:].replace(
                    "send_resolved: false", "send_resolved: true", 1
                )
                path.write_text(text, encoding="utf-8")
                validator.ALERTMANAGER = path
                with self.assertRaisesRegex(ValueError, "telegram-diagnostic"):
                    validator.validate_alertmanager_contract()
        finally:
            validator.ALERTMANAGER = original

    def test_routing_json_preserves_lane_policy(self) -> None:
        routing = json.loads(validator.ROUTING.read_text(encoding="utf-8"))
        lanes = {lane["name"]: lane for lane in routing["lanes"]}
        self.assertFalse(lanes["ticket-dashboard"]["send_resolved"])
        self.assertTrue(lanes["page"]["send_resolved"])
        self.assertTrue(lanes["page-recovery"]["send_resolved"])


if __name__ == "__main__":
    unittest.main()
