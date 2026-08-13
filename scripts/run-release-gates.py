#!/usr/bin/env python3
"""Run fail-closed user-facing release gates and write privacy-safe evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DIGEST_PREFIX = "sha256:"
CHECK_IDS = ("portfolio-health", "portfolio-homepage", "pong-user-journey")
MAX_BODY_BYTES = 64 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fail(message: str) -> None:
    raise ValueError(message)


def normalize_url(raw: str, field: str) -> str:
    if not raw or not raw.strip():
        fail(f"{field} is required")
    value = raw.strip()
    if not value.startswith(("http://", "https://")) or any(char in value for char in "\r\n"):
        fail(f"{field} must be an HTTP(S) URL")
    return value.rstrip("/")


def request_check(url: str, expected_body: str | None = None) -> tuple[bool, str]:
    request = Request(url, headers={"User-Agent": "belacca-release-gate/1", "Accept": "text/html,text/plain"})
    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
            body = response.read(MAX_BODY_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        return False, "request-failed"
    if len(body) > MAX_BODY_BYTES:
        return False, "response-too-large"
    if status != 200:
        return False, f"http-{status}"
    if expected_body is not None and body.decode("utf-8", "replace").strip() != expected_body:
        return False, "unexpected-body"
    return True, "passed"


def run_pong(command: list[str], pong_url: str) -> tuple[bool, str]:
    env = {"SYNTHETIC_BASE_URL": pong_url}
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            check=False,
            env={**__import__("os").environ, **env},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=130,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "runner-failed-or-timed-out"
    if result.returncode != 0:
        return False, f"runner-exit-{result.returncode}"
    return True, f"passed-{int((time.monotonic() - started) * 1000)}ms"


def parse_images(values: list[str]) -> dict[str, str]:
    images: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            fail("--image must be IMAGE=sha256:DIGEST")
        image, digest = value.split("=", 1)
        if not image or not digest.startswith(DIGEST_PREFIX) or len(digest) != len(DIGEST_PREFIX) + 64:
            fail(f"--image {image or '<empty>'} must use a complete sha256 digest")
        if any(char not in "0123456789abcdef" for char in digest[len(DIGEST_PREFIX):]):
            fail(f"--image {image} digest must use lowercase hexadecimal")
        images[image] = digest
    if not images:
        fail("at least one --image is required")
    return images


def parse_sources(values: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            fail("--source must be NAME=40-character-commit-sha")
        name, revision = value.split("=", 1)
        if not name or len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            fail(f"--source {name or '<empty>'} must use a lowercase 40-character commit SHA")
        sources[name] = revision
    if not sources:
        fail("at least one --source is required")
    return sources


def check_result(check_id: str, target: str, passed: bool, reason: str, started: float, evidence_uri: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "target": target,
        "passed": passed,
        "durationMs": max(0, int((time.monotonic() - started) * 1000)),
        "evidence": evidence_uri,
        "reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--stage", choices=("test", "canary", "full"), required=True)
    parser.add_argument("--portfolio-url", required=True)
    parser.add_argument("--pong-url", required=True)
    parser.add_argument("--pong-command", nargs="+", required=True, help="canonical synthetic runner command")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--flux-revision", required=True)
    parser.add_argument("--source-committed-at", required=True)
    parser.add_argument("--provenance-evidence", required=True)
    parser.add_argument("--evidence-uri", required=True)
    parser.add_argument("--readiness-passed", action="store_true")
    parser.add_argument("--provenance-verified", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        release_id = args.release_id.strip()
        if not release_id or any(char in release_id for char in "\r\n"):
            fail("release ID must be non-empty and single-line")
        portfolio = normalize_url(args.portfolio_url, "--portfolio-url")
        pong = normalize_url(args.pong_url, "--pong-url")
        sources = parse_sources(args.source)
        images = parse_images(args.image)
        if not args.flux_revision.strip() or args.flux_revision.startswith("<"):
            fail("--flux-revision must identify the reconciled Flux revision")
        try:
            source_committed_at = datetime.fromisoformat(args.source_committed_at.replace("Z", "+00:00"))
        except ValueError:
            fail("--source-committed-at must be an RFC3339 timestamp")
        if source_committed_at.tzinfo is None:
            fail("--source-committed-at must include a timezone")
        if not args.provenance_verified:
            fail("promotion blocked: --provenance-verified is required")
        if not args.readiness_passed:
            fail("promotion blocked: --readiness-passed is required")
        if not args.provenance_evidence.strip() or args.provenance_evidence.startswith("<"):
            fail("--provenance-evidence must identify immutable verification evidence")
        if not args.evidence_uri.strip() or args.evidence_uri.startswith("<"):
            fail("--evidence-uri must identify immutable release evidence")

        started_at = utc_now()
        checks: list[dict[str, Any]] = []
        check_started = time.monotonic()
        passed, reason = request_check(f"{portfolio}/health", "ok")
        checks.append(check_result("portfolio-health", f"{portfolio}/health", passed, reason, check_started, args.evidence_uri))
        check_started = time.monotonic()
        passed_home, reason_home = request_check(f"{portfolio}/")
        checks.append(check_result("portfolio-homepage", f"{portfolio}/", passed_home, reason_home, check_started, args.evidence_uri))
        check_started = time.monotonic()
        passed_pong, reason_pong = run_pong(args.pong_command, pong)
        checks.append(check_result("pong-user-journey", pong, passed_pong, reason_pong, check_started, args.evidence_uri))
        all_passed = all(check["passed"] for check in checks)
        outcome = "promoted" if all_passed else "blocked"
        evidence: dict[str, Any] = {
            "releaseId": release_id,
            "stage": args.stage,
            "sourceRevisions": sources,
            "imageDigests": images,
            "imageReferences": {image: f"{image}@{digest}" for image, digest in images.items()},
            "provenance": {
                "verifier": "cosign",
                "attestationType": "https://slsa.dev/provenance/v1",
                "verified": True,
                "verifiedImages": sorted(images),
                "evidenceUri": args.provenance_evidence,
            },
            "fluxRevision": args.flux_revision,
            "checks": checks,
            "outcome": outcome,
            "timestamps": {
                "sourceCommittedAt": args.source_committed_at,
                "productionStartedAt": started_at,
            },
        }
        if not all_passed:
            evidence["rollback"] = {
                "required": True,
                "gitChange": "required-reviewed-revert-or-forward-fix",
                "fluxReconciliation": "required-after-Git-change",
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"release gate outcome: {outcome}; evidence: {args.output}")
        return 0 if all_passed else 1
    except (OSError, ValueError) as error:
        print(f"release gates failed closed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
