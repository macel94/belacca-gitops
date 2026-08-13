#!/usr/bin/env python3
"""Validate native failure-drill evidence and calculate the recovery P95.

This validator is deliberately dependency-free and never contacts a cluster or
changes an evidence file. It accepts only sanitized evidence references and
rejects incomplete or fabricated recovery measurements.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "docs" / "NATIVE-DRILL-EVIDENCE.json"
SCHEMA_VERSION = "belacca.native-drill-evidence.v1"
TARGET_SECONDS = 360
MIN_MEASUREMENTS = 3
APPROVED_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "francesco.belacca.com",
}
EXPECTED_MEASUREMENTS = {
    "public-edge-01": ("public-edge", "belacca-k3s-02", "169.58.143.42", "edge-storage-02"),
    "control-plane-01": ("control-plane", "belacca-k3s-01", "169.58.143.41", "control-plane-01"),
    "longhorn-node-01": ("longhorn-node-degradation", "belacca-k3s-03", "169.58.143.41", "edge-storage-03"),
}
REQUIRED_CHECKS = {
    "public_health",
    "pong_api_crud",
    "pong_two_player_journey",
    "pong_cleanup",
    "flux_ready",
    "storage_health",
}
COMPLETED_STATUSES = {"passed", "missed"}
ALL_STATUSES = COMPLETED_STATUSES | {"failed", "not_executed"}


class ValidationError(ValueError):
    """A checked-in evidence contract violation."""


def fail(message: str) -> None:
    raise ValidationError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def utc_timestamp(value: Any, field: str) -> dt.datetime:
    require(isinstance(value, str) and value.endswith("Z"), f"{field} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        fail(f"{field} is not a valid timestamp: {exc}")
    require(parsed.tzinfo == dt.timezone.utc, f"{field} must use UTC")
    return parsed


def evidence_url(value: Any, field: str) -> str:
    require(nonempty(value), f"{field} must be a non-empty HTTPS URL")
    parsed = urllib.parse.urlparse(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname in APPROVED_HOSTS
        and bool(parsed.path)
        and parsed.username is None
        and parsed.password is None,
        f"{field} must be an HTTPS URL on an approved evidence host",
    )
    return value


def nearest_rank_p95(durations: list[float]) -> float | None:
    """Return nearest-rank P95, or None when no completed measurement exists."""
    if not durations:
        return None
    require(all(math.isfinite(value) and value >= 0 for value in durations), "durations must be finite non-negative numbers")
    ordered = sorted(durations)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]


def completed_measurements(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item for item in document["measurements"]
        if item.get("status") in COMPLETED_STATUSES
    ]


def validate_approval(item: Mapping[str, Any], prefix: str, *, completed: bool) -> None:
    approval = item.get("approval")
    require(isinstance(approval, dict), f"{prefix}.approval must be an object")
    if completed:
        require(approval.get("status") == "approved", f"{prefix}.approval.status must be approved for a completed measurement")
        for field in ("reference", "approved_by"):
            require(nonempty(approval.get(field)), f"{prefix}.approval.{field} is required")
        for field in ("window_start", "window_end"):
            utc_timestamp(approval.get(field), f"{prefix}.approval.{field}")
        require(
            utc_timestamp(approval["window_start"], f"{prefix}.approval.window_start")
            <= utc_timestamp(approval["window_end"], f"{prefix}.approval.window_end"),
            f"{prefix}.approval window is inverted",
        )
    else:
        require(approval.get("status") == "pending", f"{prefix}.approval.status must be pending before execution")
        for field in ("reference", "approved_by", "window_start", "window_end"):
            require(approval.get(field) is None, f"{prefix}.approval.{field} must be null before approval")


def validate_checks(item: Mapping[str, Any], prefix: str, *, completed: bool, recovery_verified_at: dt.datetime | None = None) -> None:
    checks = item.get("verification")
    require(isinstance(checks, dict), f"{prefix}.verification must be an object")
    require(set(checks) == REQUIRED_CHECKS, f"{prefix}.verification must contain exactly the required checks")
    if not completed:
        require(all(value is None for value in checks.values()), f"{prefix}.verification must be null before execution")
        return
    for check_name, check in checks.items():
        check_prefix = f"{prefix}.verification.{check_name}"
        require(isinstance(check, dict), f"{check_prefix} must be an object")
        require(check.get("status") == "pass", f"{check_prefix}.status must be pass")
        observed_at = utc_timestamp(check.get("observed_at"), f"{check_prefix}.observed_at")
        if recovery_verified_at is not None:
            require(observed_at <= recovery_verified_at, f"{check_prefix}.observed_at is after recovery verification")
        if "evidence_reference" in check:
            evidence_url(check["evidence_reference"], f"{check_prefix}.evidence_reference")


def validate_measurement(item: Any, index: int) -> None:
    prefix = f"measurements[{index}]"
    require(isinstance(item, dict), f"{prefix} must be an object")
    identifier = item.get("id")
    require(identifier in EXPECTED_MEASUREMENTS, f"{prefix}.id is not one of the required drill slots")
    expected_scenario, expected_node, expected_api_ip, expected_infra_scenario = EXPECTED_MEASUREMENTS[identifier]
    require(item.get("scenario") == expected_scenario, f"{prefix}.scenario does not match its drill slot")
    target = item.get("target")
    require(isinstance(target, dict), f"{prefix}.target must be an object")
    require(target.get("node") == expected_node, f"{prefix}.target.node does not match its drill slot")
    require(target.get("pinned_api_endpoint") == f"https://{expected_api_ip}:6443", f"{prefix}.target.pinned_api_endpoint does not match its drill slot")
    require(target.get("infrastructure_scenario") == expected_infra_scenario, f"{prefix}.target.infrastructure_scenario does not match its drill slot")
    require(nonempty(target.get("address")), f"{prefix}.target.address is required")
    require(target.get("address") in {"169.58.97.73", "169.58.143.41", "169.58.143.42"}, f"{prefix}.target.address is not a native node address")
    for field in ("owner", "mutation_owner", "observer", "rollback"):
        require(nonempty(item.get(field)), f"{prefix}.{field} is required")

    status = item.get("status")
    require(status in ALL_STATUSES, f"{prefix}.status is invalid")
    completed = status in COMPLETED_STATUSES
    mutation_executed = item.get("mutation_executed")
    require(mutation_executed is completed or (status in {"failed", "not_executed"} and mutation_executed is False), f"{prefix}.mutation_executed is inconsistent with status")
    validate_approval(item, prefix, completed=completed)

    abort = item.get("abort_threshold")
    require(isinstance(abort, dict), f"{prefix}.abort_threshold must be an object")
    require(abort.get("recovery_timeout_seconds") == TARGET_SECONDS, f"{prefix}.abort_threshold must use the 360 second objective")
    require(isinstance(abort.get("conditions"), list) and abort["conditions"], f"{prefix}.abort_threshold.conditions must be non-empty")

    timings = item.get("timings")
    require(isinstance(timings, dict), f"{prefix}.timings must be an object")
    start = timings.get("fault_injection_confirmed_at")
    stop = timings.get("recovery_verified_at")
    duration = timings.get("recovery_seconds")
    baseline = item.get("baseline")
    recovery = item.get("recovery")
    if completed:
        for phase_name, phase in (("baseline", baseline), ("recovery", recovery)):
            phase_prefix = f"{prefix}.{phase_name}"
            require(isinstance(phase, dict), f"{phase_prefix} must be an object")
            require(phase.get("status") == "pass", f"{phase_prefix}.status must be pass")
            phase_time = utc_timestamp(phase.get("observed_at"), f"{phase_prefix}.observed_at")
            if phase_name == "recovery":
                require(phase_time <= utc_timestamp(stop, f"{prefix}.timings.recovery_verified_at"), f"{phase_prefix}.observed_at is after recovery verification")
        start_time = utc_timestamp(start, f"{prefix}.timings.fault_injection_confirmed_at")
        stop_time = utc_timestamp(stop, f"{prefix}.timings.recovery_verified_at")
        require(stop_time >= start_time, f"{prefix}.timings recovery precedes fault confirmation")
        require(isinstance(duration, (int, float)) and not isinstance(duration, bool), f"{prefix}.timings.recovery_seconds must be numeric")
        expected_duration = (stop_time - start_time).total_seconds()
        require(abs(float(duration) - expected_duration) <= 0.001, f"{prefix}.timings.recovery_seconds does not match UTC timestamps")
        require(math.isfinite(float(duration)) and float(duration) >= 0, f"{prefix}.timings.recovery_seconds must be finite and non-negative")
        validate_checks(item, prefix, completed=True, recovery_verified_at=stop_time)
        if status == "passed":
            require(float(duration) < TARGET_SECONDS, f"{prefix} passed measurement must be under 360 seconds")
        if status == "missed":
            require(float(duration) >= TARGET_SECONDS, f"{prefix} missed measurement must be at least 360 seconds")
    else:
        require(start is None and stop is None and duration is None, f"{prefix}.timings must be null before a completed recovery")
        require(baseline is None and recovery is None, f"{prefix}.baseline and recovery must be null before execution")
        validate_checks(item, prefix, completed=False)

    dns = item.get("dns_fallback")
    require(isinstance(dns, dict) and isinstance(dns.get("used"), bool), f"{prefix}.dns_fallback must declare used")
    if dns["used"]:
        require(nonempty(dns.get("record_reference")), f"{prefix}.dns_fallback.record_reference is required when used")
        utc_timestamp(dns.get("restored_at"), f"{prefix}.dns_fallback.restored_at")
    else:
        require(dns.get("record_reference") is None and dns.get("restored_at") is None, f"{prefix}.dns_fallback unused fields must be null")

    report = item.get("infrastructure_report")
    if completed or status == "failed":
        evidence_url(report, f"{prefix}.infrastructure_report")
    else:
        require(report is None, f"{prefix}.infrastructure_report must be null before execution")

    references = item.get("evidence_references")
    require(isinstance(references, list) and len(references) == len(set(references)), f"{prefix}.evidence_references must be a list without duplicates")
    for ref_index, reference in enumerate(references):
        evidence_url(reference, f"{prefix}.evidence_references[{ref_index}]")
    if completed or status == "failed":
        require(references, f"{prefix}.evidence_references is required for executed measurements")
    else:
        require(not references, f"{prefix}.evidence_references must be empty before execution")

    postmortem = item.get("postmortem_reference")
    if status in {"missed", "failed"}:
        evidence_url(postmortem, f"{prefix}.postmortem_reference")
    else:
        require(postmortem is None, f"{prefix}.postmortem_reference must be null unless the measurement missed or failed")


def calculate_summary(document: Mapping[str, Any]) -> dict[str, Any]:
    completed = completed_measurements(document)
    durations = [float(item["timings"]["recovery_seconds"]) for item in completed]
    p95 = nearest_rank_p95(durations)
    if len(durations) < MIN_MEASUREMENTS:
        status = "not_available"
        acceptance = "pending"
    elif p95 is not None and p95 < TARGET_SECONDS:
        status = "under_target"
        acceptance = "passed"
    else:
        status = "missed"
        acceptance = "corrective_action_required"
    return {
        "comparable_measurements": len(durations),
        "durations_seconds": durations,
        "p95_seconds": p95,
        "p95_status": status,
        "acceptance_status": acceptance,
    }


def validate_document(document: Any) -> dict[str, Any]:
    require(isinstance(document, dict), "evidence document must be an object")
    require(document.get("schema_version") == SCHEMA_VERSION, "unsupported native drill evidence schema")
    require(document.get("environment") == "native-production", "evidence must identify native-production")
    require(nonempty(document.get("issue")) and document["issue"].startswith("https://github.com/"), "issue must be a GitHub HTTPS URL")

    boundary = document.get("availability_boundary")
    require(isinstance(boundary, dict), "availability_boundary must be an object")
    require(boundary.get("drill_results_included_in_availability") is False, "drill results must remain outside availability accounting")
    require(nonempty(boundary.get("external_slo_source")), "external_slo_source is required")
    require("Recovery drills" in boundary.get("statement", ""), "availability boundary statement is missing")

    objective = document.get("objective")
    require(isinstance(objective, dict), "objective must be an object")
    require(objective.get("target_seconds_exclusive") == TARGET_SECONDS, "objective target must be 360 seconds exclusive")
    require(objective.get("minimum_comparable_measurements") == MIN_MEASUREMENTS, "objective must require three measurements")
    require(objective.get("p95_method") == "nearest-rank: sort durations and select rank ceil(0.95 * n)", "objective must declare nearest-rank P95")
    required_checks = document.get("required_checks")
    require(isinstance(required_checks, list) and set(required_checks) == REQUIRED_CHECKS and len(required_checks) == len(REQUIRED_CHECKS), "required_checks must exactly match the declared check set")
    evidence_hosts = document.get("approved_evidence_hosts")
    require(isinstance(evidence_hosts, list) and set(evidence_hosts) == APPROVED_HOSTS and len(evidence_hosts) == len(APPROVED_HOSTS), "approved evidence hosts must be explicit")

    measurements = document.get("measurements")
    require(isinstance(measurements, list) and len(measurements) == len(EXPECTED_MEASUREMENTS), "evidence must contain exactly three drill slots")
    seen: set[str] = set()
    for index, item in enumerate(measurements):
        validate_measurement(item, index)
        identifier = item["id"]
        require(identifier not in seen, f"duplicate measurement id: {identifier}")
        seen.add(identifier)
    require(seen == set(EXPECTED_MEASUREMENTS), "evidence must contain the public edge, control-plane, and Longhorn slots")

    calculated = calculate_summary(document)
    summary = document.get("summary")
    require(isinstance(summary, dict), "summary must be an object")
    for key, value in calculated.items():
        require(summary.get(key) == value, f"summary.{key} does not match calculated evidence")
    require(summary.get("acceptance_status") != "passed" or calculated["p95_status"] == "under_target", "summary cannot claim acceptance without an under-target P95")
    return calculated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--json", action="store_true", dest="as_json", help="print the calculated summary as JSON")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
        summary = validate_document(document)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        print(f"native drill evidence validation failed: {error}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"validated native drill evidence: {summary['comparable_measurements']} comparable measurements; "
            f"p95={summary['p95_seconds']!r}; status={summary['p95_status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
