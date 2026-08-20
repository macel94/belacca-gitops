#!/usr/bin/env python3
"""Validate the GitOps contract for the hosted Mutandae demo."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = Path("/root/sources/mutandae/deploy/k3s")
CLUSTER = ROOT / "clusters/belacca-production"


def require(path: Path, text: str) -> None:
    content = path.read_text()
    if text not in content:
        raise SystemExit(f"{path}: missing {text!r}")


def main() -> int:
    app_kustomization = APP / "kustomization.yaml"
    require(app_kustomization, "deployment-preview.yaml")
    require(app_kustomization, "service-preview.yaml")
    require(APP / "deployment.yaml", "value: live")
    require(APP / "deployment-preview.yaml", "value: preview")
    for path in (APP / "deployment.yaml", APP / "deployment-preview.yaml"):
        require(path, "name: REDIS_URL")
        require(path, "name: mutandae-redis-auth")
        require(path, "key: REDIS_URL")

    redis = CLUSTER / "mutandae" / "redis.yaml"
    require(redis, "kind: StatefulSet")
    require(redis, "name: mutandae-redis")
    require(redis, "storageClassName: longhorn")
    require(redis, "image: redis:7.4.2-alpine@sha256:")
    require(redis, "name: mutandae-redis-auth")
    require(redis, "REDISCLI_AUTH=\\\"$REDIS_PASSWORD\\\" redis-cli ping")
    if 'redis-cli -a "' in redis.read_text():
        raise SystemExit(f"{redis}: Redis probes must use REDISCLI_AUTH, not -a")

    secret = CLUSTER / "mutandae" / "redis-secret.yaml"
    secret_text = secret.read_text()
    require(secret, "name: mutandae-redis-auth")
    if "ENC[AES256_GCM" not in secret_text:
        raise SystemExit(f"{secret}: Redis credentials must remain SOPS encrypted")
    if "redis://:" in secret_text and "ENC[AES256_GCM" not in secret_text:
        raise SystemExit(f"{secret}: plaintext Redis URL detected")

    require(CLUSTER / "mutandae" / "network-policy.yaml", "name: mutandae-default-deny")
    require(CLUSTER / "mutandae" / "network-policy.yaml", "name: mutandae-redis-traffic")
    require(CLUSTER / "mutandae" / "network-policy.yaml", "cidr: 169.58.97.73/32")
    require(CLUSTER / "mutandae" / "network-policy.yaml", "cidr: 169.58.143.41/32")
    require(CLUSTER / "mutandae" / "network-policy.yaml", "cidr: 169.58.143.42/32")
    ingress = CLUSTER / "routing" / "mutandae-ingress.yaml"
    require(ingress, "name: mutandae-preview")
    require(ingress, "host: preview.mutandae.com")
    require(ingress, "host: mutandae.com")

    require(CLUSTER / "kustomization.yaml", "  - mutandae")
    if "native-mutandae-persistence" in (CLUSTER / "native-platform-applications.yaml").read_text():
        raise SystemExit("persistence overlay must remain owned by the native root Kustomization")
    require(CLUSTER / "mutandae" / "kustomization.yaml", "redis-secret.yaml")
    print("validated Mutandae Redis persistence, environment isolation, routing, and Flux contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
