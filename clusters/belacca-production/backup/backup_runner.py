#!/usr/bin/env python3
"""Fail-closed encrypted SQLite backup and restore verification utility.

Only Python's standard library is required. S3-compatible requests use
Signature Version 4, HTTPS is mandatory, and writer/restore credentials are
selected explicitly by the operation. No secret values are logged.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.server
import json
import os
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

SERVICES = {"pong", "goatcounter", "dex"}
REQUIRED_METADATA = {
    "schema", "service", "created_at", "source_sha256", "sqlite_integrity",
    "source_revision", "image_digests", "runbook",
}


def fail(message: str) -> NoReturn:
    print(f"backup-runner: {message}", file=sys.stderr)
    raise SystemExit(1)


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        fail(f"required environment variable is missing: {name}")
    return value


def gate() -> None:
    if required("BACKUP_AUTOMATION_ENABLED") != "true":
        fail("BACKUP_AUTOMATION_ENABLED must be exactly true after external prerequisite review")
    if required("BACKUP_CONSISTENCY_ACKNOWLEDGED") != "true":
        fail("BACKUP_CONSISTENCY_ACKNOWLEDGED must be exactly true after an approved quiesced-copy procedure")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integrity_connection(connection: sqlite3.Connection, label: str) -> None:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    if not row or row[0] != "ok":
        fail(f"SQLite integrity check failed for {label}: {row!r}")


def integrity(path: Path) -> None:
    if not path.is_file():
        fail(f"SQLite file does not exist: {path}")
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
            integrity_connection(db, str(path))
    except sqlite3.Error as exc:
        fail(f"SQLite integrity check failed for {path}: {exc}")


def online_backup(source: Path, destination: Path) -> None:
    """Make a new SQLite file through the online backup API."""
    if not source.is_file():
        fail(f"SQLite source does not exist: {source}")
    try:
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as source_db, sqlite3.connect(destination) as destination_db:
            integrity_connection(source_db, f"source {source}")
            source_db.backup(destination_db)
            integrity_connection(destination_db, f"backup {destination}")
    except sqlite3.Error as exc:
        fail(f"SQLite online backup failed: {exc}")


def safe_prefix(value: str) -> str:
    value = value.strip("/")
    if not value or any(part in {".", ".."} for part in value.split("/")):
        fail("object prefix must be non-empty and must not contain dot path components")
    return value


def timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def metadata(service: str, artifact: Path, source_revision: str, image_digests: str) -> dict[str, object]:
    return {
        "schema": "belacca.backup.v1",
        "service": service,
        "created_at": timestamp(),
        "source_sha256": sha256(artifact),
        "sqlite_integrity": "ok",
        "source_revision": source_revision,
        "image_digests": image_digests,
        "runbook": "docs/BACKUP-RUNBOOK.md",
    }


class S3:
    """Minimal path-style S3 client with explicit credentials."""

    def __init__(self, restore: bool = False) -> None:
        suffix = "_RESTORE" if restore else ""
        self.endpoint = required(f"S3{suffix}_ENDPOINT")
        if not self.endpoint.startswith("https://"):
            fail(f"S3{suffix}_ENDPOINT must use https://")
        self.region = required(f"S3{suffix}_REGION")
        self.bucket = required(f"S3{suffix}_BUCKET")
        self.prefix = safe_prefix(required(f"S3{suffix}_PREFIX"))
        self.access = required(f"S3{suffix}_ACCESS_KEY_ID")
        self.secret = required(f"S3{suffix}_SECRET_ACCESS_KEY")
        self.restore = restore

    def key(self, key: str) -> str:
        if not key or ".." in key.split("/"):
            fail("unsafe object key")
        if not key.startswith(self.prefix + "/"):
            fail("object key is outside the configured prefix")
        return key

    def request(self, method: str, key: str = "", body: bytes = b"", query: str = "", extra: dict[str, str] | None = None) -> bytes:
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        path = "/" + urllib.parse.quote(self.bucket, safe="")
        if key:
            path += "/" + urllib.parse.quote(self.key(key), safe="/")
        host = urllib.parse.urlsplit(self.endpoint).netloc
        headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
        if extra:
            headers.update({k.lower(): v for k, v in extra.items()})
        canonical_headers = "".join(f"{k}:{' '.join(v.strip().split())}\n" for k, v in sorted(headers.items()))
        signed = ";".join(sorted(headers))
        canonical = "\n".join((method, path, query, canonical_headers, signed, payload_hash))
        scope = f"{date}/{self.region}/s3/aws4_request"
        def sign(value: bytes, key_bytes: bytes) -> bytes:
            return hmac.new(key_bytes, value, hashlib.sha256).digest()
        k_date = sign(date.encode(), b"AWS4" + self.secret.encode())
        k_region = sign(self.region.encode(), k_date)
        k_service = sign(b"s3", k_region)
        signing_key = sign(b"aws4_request", k_service)
        signature = hmac.new(signing_key, ("AWS4-HMAC-SHA256\n" + amz_date + "\n" + scope + "\n" + hashlib.sha256(canonical.encode()).hexdigest()).encode(), hashlib.sha256).hexdigest()
        headers["authorization"] = f"AWS4-HMAC-SHA256 Credential={self.access}/{scope}, SignedHeaders={signed}, Signature={signature}"
        url = self.endpoint.rstrip("/") + path + ("?" + query if query else "")
        request = urllib.request.Request(url, data=body if method in {"PUT", "POST"} else None, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(512).decode("utf-8", "replace")
            fail(f"S3 {method} request failed with HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as exc:
            fail(f"S3 {method} request failed: {exc}")

    def put(self, key: str, body: bytes, encrypted: bool = True) -> None:
        headers = {"content-type": "application/octet-stream"}
        if encrypted:
            headers.update({
                "x-amz-server-side-encryption": "aws:kms",
                "x-amz-server-side-encryption-aws-kms-key-id": required("S3_KMS_KEY_ID"),
                "x-amz-server-side-encryption-context": required("S3_ENCRYPTION_CONTEXT"),
            })
        self.request("PUT", key, body, extra=headers)

    def get(self, key: str) -> bytes:
        return self.request("GET", key)

    def list_keys(self, prefix: str) -> list[str]:
        safe = safe_prefix(prefix)
        values = {"list-type": "2", "prefix": safe + "/", "max-keys": "1000"}
        query = urllib.parse.urlencode(sorted(values.items()))
        root = ET.fromstring(self.request("GET", query=query))
        return [element.text or "" for element in root.findall("{*}Contents/{*}Key")]


def key_for(client: S3, service: str, created_at: str) -> str:
    stamp = created_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
    return f"{client.prefix}/{service}/{stamp}-{os.getpid()}.sqlite"


def upload(service: str, source: Path, revision: str, images: str) -> None:
    started = time.monotonic()
    started_at = timestamp()
    gate()
    client = S3()
    with tempfile.TemporaryDirectory(prefix="backup-upload-") as directory:
        artifact = Path(directory) / f"{service}.sqlite"
        online_backup(source, artifact)
        data = metadata(service, artifact, revision, images)
        key = key_for(client, service, str(data["created_at"]))
        client.put(key, artifact.read_bytes())
        client.put(key + ".manifest.json", (json.dumps(data, sort_keys=True, indent=2) + "\n").encode())
        print(json.dumps({"service": service, "key": key, "sha256": data["source_sha256"], "created_at": data["created_at"], "source_revision": revision, "image_digests": images, "integrity": "ok", "started_at": started_at, "finished_at": timestamp(), "duration_seconds": round(time.monotonic() - started, 3)}, sort_keys=True))


def validate_manifest(data: object, service: str, artifact: Path) -> dict[str, object]:
    if not isinstance(data, dict) or REQUIRED_METADATA - set(data):
        fail("manifest is missing required metadata")
    if data["schema"] != "belacca.backup.v1" or data["service"] != service:
        fail("manifest schema or service does not match requested restore")
    if data["sqlite_integrity"] != "ok" or data["source_sha256"] != sha256(artifact):
        fail("artifact hash or recorded SQLite integrity does not match")
    return data


def download(service: str, key: str, destination: Path) -> None:
    started = time.monotonic()
    started_at = timestamp()
    gate()
    client = S3(restore=True)
    with tempfile.TemporaryDirectory(prefix="backup-download-") as directory:
        root = Path(directory)
        artifact = root / "artifact.sqlite"
        artifact.write_bytes(client.get(key))
        manifest = json.loads(client.get(key + ".manifest.json"))
        validate_manifest(manifest, service, artifact)
        integrity(artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        online_backup(artifact, destination)
        print(json.dumps({"service": service, "key": key, "sha256": sha256(destination), "integrity": "ok", "started_at": started_at, "finished_at": timestamp(), "duration_seconds": round(time.monotonic() - started, 3)}, sort_keys=True))


def newest_manifest(client: S3, service: str) -> tuple[str, dict[str, object]]:
    service_prefix = f"{client.prefix}/{service}"
    candidates: list[tuple[datetime, str, dict[str, object]]] = []
    for key in client.list_keys(service_prefix):
        if not key.endswith(".manifest.json"):
            continue
        try:
            data = json.loads(client.get(key))
            if data.get("service") != service or data.get("schema") != "belacca.backup.v1":
                continue
            created = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
            candidates.append((created, key, data))
        except (KeyError, ValueError, json.JSONDecodeError, ET.ParseError):
            continue
    if not candidates:
        fail(f"no usable verified manifest found for {service}")
    for created, key, data in sorted(candidates, reverse=True):
        if time.time() - created.timestamp() > 93600:
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="backup-candidate-") as directory:
                artifact = Path(directory) / "candidate.sqlite"
                artifact.write_bytes(client.get(key[:-len(".manifest.json")]))
                validate_manifest(data, service, artifact)
                integrity(artifact)
            return key, data
        except SystemExit:
            # Quarantine this candidate operationally and try the next verified one.
            continue
    fail(f"no fresh, integrity-verified artifact found for {service}")


def restore_verify(service: str) -> None:
    started = time.monotonic()
    started_at = timestamp()
    gate()
    client = S3(restore=True)
    key, manifest = newest_manifest(client, service)
    with tempfile.TemporaryDirectory(prefix=f"{service}-restore-rehearsal-") as directory:
        artifact = Path(directory) / f"{service}.sqlite"
        artifact.write_bytes(client.get(key[:-len(".manifest.json")]))
        validate_manifest(manifest, service, artifact)
        verify(service, artifact)
        print(json.dumps({"service": service, "key": key[:-len('.manifest.json')], "artifact_sha256": sha256(artifact), "source_revision": manifest["source_revision"], "image_digests": manifest["image_digests"], "integrity": "ok", "isolated_target": True, "started_at": started_at, "finished_at": timestamp(), "duration_seconds": round(time.monotonic() - started, 3)}, sort_keys=True))


def verify(service: str, artifact: Path) -> None:
    if service not in SERVICES:
        fail(f"unsupported service: {service}")
    integrity(artifact)
    with tempfile.TemporaryDirectory(prefix=f"{service}-restore-target-") as directory:
        restored = Path(directory) / f"{service}.sqlite"
        online_backup(artifact, restored)
        with sqlite3.connect(f"file:{restored.resolve()}?mode=ro", uri=True) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(json.dumps({"service": service, "sha256": sha256(artifact), "integrity": "ok", "isolated_target": True, "tables": tables}, sort_keys=True))


def freshness(max_age_seconds: int, service: str, key: str, created_at: str) -> None:
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"invalid created_at: {exc}")
    age = time.time() - created.timestamp()
    if age > max_age_seconds or age < -300:
        fail(f"stale or future backup for {service}: age={int(age)}s key={key}")
    print(json.dumps({"service": service, "key": key, "age_seconds": int(age), "fresh": True}, sort_keys=True))


def restore_configuration_ready() -> bool:
    required_names = (
        "BACKUP_AUTOMATION_ENABLED",
        "BACKUP_CONSISTENCY_ACKNOWLEDGED",
        "S3_RESTORE_ENDPOINT",
        "S3_RESTORE_BUCKET",
        "S3_RESTORE_PREFIX",
        "S3_RESTORE_REGION",
        "S3_RESTORE_ACCESS_KEY_ID",
        "S3_RESTORE_SECRET_ACCESS_KEY",
    )
    if any(not os.environ.get(name, "").strip() for name in required_names):
        return False
    if os.environ["BACKUP_AUTOMATION_ENABLED"].strip() != "true" or os.environ["BACKUP_CONSISTENCY_ACKNOWLEDGED"].strip() != "true":
        return False
    endpoint = os.environ["S3_RESTORE_ENDPOINT"].strip()
    prefix = os.environ["S3_RESTORE_PREFIX"].strip().strip("/")
    return endpoint.startswith("https://") and bool(prefix) and not any(part in {".", ".."} for part in prefix.split("/"))


def metrics_server() -> None:
    port = int(os.environ.get("METRICS_PORT", "9091"))
    def collect() -> str:
        configured = restore_configuration_ready()
        client = S3(restore=True) if configured else None
        lines = ["# HELP belacca_backup_configuration_ready Whether the externally provisioned restore Secret and runtime gates are ready.", "# TYPE belacca_backup_configuration_ready gauge", f"belacca_backup_configuration_ready {int(configured)}"]
        lines += ["# HELP belacca_backup_last_success_timestamp_seconds Unix timestamp of the newest verified backup.", "# TYPE belacca_backup_last_success_timestamp_seconds gauge"]
        lines += ["# HELP belacca_backup_integrity_ok Whether the newest artifact and manifest verify.", "# TYPE belacca_backup_integrity_ok gauge"]
        lines += ["# HELP belacca_backup_daily_retention_count Number of daily verified artifacts found.", "# TYPE belacca_backup_daily_retention_count gauge"]
        lines += ["# HELP belacca_backup_monthly_retention_count Number of distinct UTC months with verified artifacts.", "# TYPE belacca_backup_monthly_retention_count gauge"]
        for service in sorted(SERVICES):
            if not configured or client is None:
                lines.append(f'belacca_backup_last_success_timestamp_seconds{{service="{service}"}} 0')
                lines.append(f'belacca_backup_integrity_ok{{service="{service}"}} 0')
                lines.append(f'belacca_backup_daily_retention_count{{service="{service}"}} 0')
                lines.append(f'belacca_backup_monthly_retention_count{{service="{service}"}} 0')
                continue
            latest = None
            ok = 0
            for key in client.list_keys(f"{client.prefix}/{service}"):
                if not key.endswith(".manifest.json"):
                    continue
                try:
                    data = json.loads(client.get(key))
                    if data.get("service") != service:
                        continue
                    created = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
                    if latest is None or created > latest[0]: latest = (created, key, data)
                except (KeyError, ValueError, json.JSONDecodeError, ET.ParseError):
                    continue
            if latest:
                try:
                    artifact = client.get(latest[1][:-len(".manifest.json")])
                    ok = int(hashlib.sha256(artifact).hexdigest() == latest[2].get("source_sha256") and latest[2].get("sqlite_integrity") == "ok")
                except SystemExit:
                    ok = 0
                lines.append(f'belacca_backup_last_success_timestamp_seconds{{service="{service}"}} {latest[0].timestamp()}')
                lines.append(f'belacca_backup_integrity_ok{{service="{service}"}} {ok}')
            else:
                lines.append(f'belacca_backup_last_success_timestamp_seconds{{service="{service}"}} 0')
                lines.append(f'belacca_backup_integrity_ok{{service="{service}"}} 0')
            manifests = [k for k in client.list_keys(f"{client.prefix}/{service}") if k.endswith(".manifest.json")]
            days = set()
            months = set()
            for key in manifests:
                try:
                    item = json.loads(client.get(key))
                    artifact = client.get(key[:-len(".manifest.json")])
                    if item.get("sqlite_integrity") == "ok" and hashlib.sha256(artifact).hexdigest() == item.get("source_sha256"):
                        created = str(item["created_at"])
                        days.add(created[:10])
                        months.add(created[:7])
                except (KeyError, ValueError, json.JSONDecodeError):
                    continue
            daily = len(days)
            lines.append(f'belacca_backup_daily_retention_count{{service="{service}"}} {daily}')
            lines.append(f'belacca_backup_monthly_retention_count{{service="{service}"}} {len(months)}')
        return "\n".join(lines) + "\n"
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/metrics": self.send_error(404); return
            payload = collect().encode()
            self.send_response(200); self.send_header("Content-Type", "text/plain; version=0.0.4"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
        def log_message(self, *_: object) -> None: return
    http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="backup-runner-test-") as directory:
        root = Path(directory); source = root / "source.sqlite"; copy = root / "copy.sqlite"
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE evidence (value TEXT NOT NULL)"); db.execute("INSERT INTO evidence VALUES ('deterministic')")
        online_backup(source, copy); verify("pong", copy)
        with sqlite3.connect(copy) as db:
            row = db.execute("SELECT value FROM evidence").fetchone()
        if row != ("deterministic",): fail(f"self-test data mismatch: {row!r}")
    print("backup runner self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("upload"); p.add_argument("service", choices=sorted(SERVICES)); p.add_argument("source", type=Path); p.add_argument("--source-revision", required=True); p.add_argument("--image-digests", required=True)
    p = sub.add_parser("download"); p.add_argument("service", choices=sorted(SERVICES)); p.add_argument("key"); p.add_argument("destination", type=Path)
    p = sub.add_parser("verify"); p.add_argument("service", choices=sorted(SERVICES)); p.add_argument("artifact", type=Path)
    p = sub.add_parser("freshness"); p.add_argument("service", choices=sorted(SERVICES)); p.add_argument("key"); p.add_argument("created_at"); p.add_argument("--max-age-seconds", type=int, default=93600)
    p = sub.add_parser("restore-verify"); p.add_argument("service", choices=sorted(SERVICES))
    sub.add_parser("metrics-server"); sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "upload": upload(args.service, args.source, args.source_revision, args.image_digests)
    elif args.command == "download": download(args.service, args.key, args.destination)
    elif args.command == "verify": verify(args.service, args.artifact)
    elif args.command == "freshness": freshness(args.max_age_seconds, args.service, args.key, args.created_at)
    elif args.command == "restore-verify": restore_verify(args.service)
    elif args.command == "metrics-server": metrics_server()
    else: self_test()


if __name__ == "__main__":
    main()
