#!/usr/bin/env python3
"""Deterministic tests for the native edge failover contract."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-edge-failover.py"
CONTRACT = ROOT / "clusters/belacca-production/edge/failover-contract.json"
EVIDENCE = ROOT / "docs/evidence/api-edge-failover.json"

spec = importlib.util.spec_from_file_location("validate_edge_failover", SCRIPT)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class EdgeFailoverContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_checked_in_contract_and_pending_evidence_are_valid(self) -> None:
        validator.validate_contract(self.contract)
        validator.validate_evidence(self.evidence)

    def test_private_ports_cannot_become_public(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["networkBoundary"]["publicListenerPorts"].append(2379)
        with self.assertRaises(ValueError):
            validator.validate_contract(contract)

    def test_kubeconfig_and_certificate_must_use_stable_api_name(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["endpoints"]["api"]["certificateSAN"] = "169.58.143.41"
        with self.assertRaises(ValueError):
            validator.validate_contract(contract)

    def test_pending_evidence_cannot_claim_a_provider_vip(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["providerVip"] = "192.0.2.10"
        with self.assertRaises(ValueError):
            validator.validate_evidence(evidence)

    def test_pending_evidence_cannot_contain_a_completed_scenario(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["scenarios"]["one-edge-failure"]["status"] = "complete"
        with self.assertRaises(ValueError):
            validator.validate_evidence(evidence)

    def test_not_run_scenario_cannot_contain_measurements(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["scenarios"]["one-edge-failure"]["measurements"]["failureToWithdrawSeconds"] = 15
        with self.assertRaises(ValueError):
            validator.validate_evidence(evidence)

    def test_complete_evidence_requires_failure_injection_and_nonnegative_values(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["status"] = "complete"
        evidence["providerVip"] = "192.0.2.10"
        evidence["observedAtUtc"] = "2026-01-01T00:00:00Z"
        evidence["operator"] = "operator-id"
        for scenario in evidence["scenarios"].values():
            scenario["status"] = "complete"
            scenario["failureInjected"] = True
            for field in scenario["measurements"]:
                scenario["measurements"][field] = 1
        for scenario in evidence["scenarios"].values():
            scenario["portsChecked"] = [80, 443, 6443]
        validator.validate_evidence(evidence)
        evidence["scenarios"]["one-edge-failure"]["measurements"]["recoveryToReaddSeconds"] = -1
        with self.assertRaises(ValueError):
            validator.validate_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
