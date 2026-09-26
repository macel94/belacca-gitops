#!/usr/bin/env python3
"""Validate Mutandae's intake app/cluster contract without cluster access."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = ROOT / "clusters" / "belacca-production"
APP = Path(os.environ.get("MUTANDAE_SOURCE_ROOT", "/root/sources/mutandae")) / "deploy" / "k3s"
MUTANDAE = CLUSTER / "mutandae"
DEX = CLUSTER / "dex"


def require(path: Path, text: str) -> None:
    if text not in path.read_text(encoding="utf-8"):
        raise SystemExit(f"{path}: missing {text!r}")


def encrypted_secret(path: Path, name: str) -> None:
    text = path.read_text(encoding="utf-8")
    require(path, f"name: {name}")
    if "ENC[AES256_GCM" not in text or "sops:" not in text:
        raise SystemExit(f"{path}: secret must remain SOPS encrypted")
    if "PLACEHOLDER" in text:
        raise SystemExit(f"{path}: placeholder secret value is not deployable")


def validate_app_source() -> None:
    if not APP.is_dir():
        print("Mutandae source checkout unavailable; app-manifest checks skipped")
        return
    kustomization = APP / "kustomization.yaml"
    for resource in ("deployment.yaml", "deployment-preview.yaml", "service.yaml", "service-preview.yaml"):
        require(kustomization, resource)
    for name, environment, secret, db_secret, owner_role, app_role, database, claim in (
        ("deployment.yaml", "live", "mutandae-intake-live", "mutandae-live-database-credentials", "mutandae_live_owner", "mutandae_live_app", "mutandae_live", "mutandae-live-documents"),
        ("deployment-preview.yaml", "preview", "mutandae-intake-preview", "mutandae-preview-database-credentials", "mutandae_preview_owner", "mutandae_preview_app", "mutandae_preview", "mutandae-preview-documents"),
    ):
        path = APP / name
        for fragment in (
            f"value: {environment}", "value: oidc", "name: DATABASE_URL", 'value: ""', f"name: {secret}",
            "name: MUTANDAE_INTAKE_ENCRYPTION_KEY", "name: MUTANDAE_DOCUMENT_ENCRYPTION_KEY",
            "name: MUTANDAE_DOCUMENT_SIGNING_KEY", "name: MUTANDAE_DOCUMENT_ROOT",
            "name: database-migrate", "name: MUTANDAE_MIGRATOR_DATABASE_USER", owner_role,
            "name: MUTANDAE_MIGRATOR_DATABASE_SSLMODE", "value: verify-full", "name: MUTANDAE_MIGRATOR_DATABASE_SSLROOTCERT",
            f"name: {db_secret}", f"name: MUTANDAE_DATABASE_USER", app_role,
            "name: MUTANDAE_DATABASE_SSLMODE", "name: MUTANDAE_DATABASE_SSLROOTCERT", f"value: {database}",
            "name: postgres-ca", "name: mutandae-postgres-ca", "/etc/mutandae/postgres-ca/ca.crt",
            f"claimName: {claim}", "readOnlyRootFilesystem: true",
        ):
            require(path, fragment)
        for legacy in ("AWS_ACCESS_KEY_ID", "GCP_SERVICE_ACCOUNT_KEY_JSON", "AZURE_CLIENT_SECRET", "VAULT_TOKEN", "REDIS_URL"):
            if legacy in path.read_text(encoding="utf-8"):
                raise SystemExit(f"{path}: old cloud/Redis/Vault variable remains: {legacy}")


def main() -> int:
    validate_app_source()
    kustomization = MUTANDAE / "kustomization.yaml"
    for resource in (
        "postgres.yaml", "postgres-ca.yaml", "postgres-tls-secret.yaml", "postgres-secret.yaml",
        "postgres-live-secret.yaml", "postgres-preview-secret.yaml", "network-policy-postgres.yaml",
        "documents-pvc.yaml", "intake-live-secret.yaml", "intake-preview-secret.yaml",
    ):
        require(kustomization, resource)
    postgres = MUTANDAE / "postgres.yaml"
    for fragment in (
        "kind: StatefulSet", "name: mutandae-postgres",
        "postgres:17.11-alpine3.24@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24",
        "storageClassName: longhorn", "mutandae_live_owner", "mutandae_live_app",
        "mutandae_preview_owner", "mutandae_preview_app", "NOBYPASSRLS",
        "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC", "REVOKE CONNECT ON DATABASE template1 FROM PUBLIC",
        "REVOKE CONNECT ON DATABASE mutandae_live FROM PUBLIC", "REVOKE CONNECT ON DATABASE mutandae_preview FROM PUBLIC",
        "ssl=on", "ssl_cert_file=/etc/postgres-tls/tls.crt", "ssl_key_file=/etc/postgres-tls/tls.key",
        "PG_TLS_CERT", "PG_TLS_KEY", "mutandae-postgres-tls", "mutandae_live", "mutandae_preview",
        "runAsNonRoot: true", "runAsUser: 70",
    ):
        require(postgres, fragment)
    postgres_admin_secret = MUTANDAE / "postgres-secret.yaml"
    for stale_key in ("MUTANDAE_OWNER_PASSWORD", "MUTANDAE_RUNTIME_PASSWORD"):
        if stale_key in postgres_admin_secret.read_text(encoding="utf-8"):
            raise SystemExit(f"{postgres_admin_secret}: shared legacy DB credential remains: {stale_key}")
    for path, name in (
        (postgres_admin_secret, "mutandae-postgres-credentials"),
        (MUTANDAE / "postgres-live-secret.yaml", "mutandae-live-database-credentials"),
        (MUTANDAE / "postgres-preview-secret.yaml", "mutandae-preview-database-credentials"),
        (MUTANDAE / "postgres-tls-secret.yaml", "mutandae-postgres-tls"),
        (MUTANDAE / "intake-live-secret.yaml", "mutandae-intake-live"),
        (MUTANDAE / "intake-preview-secret.yaml", "mutandae-intake-preview"),
        (DEX / "secret-mutandae-client.yaml", "mutandae-dex-client-secret"),
    ):
        encrypted_secret(path, name)
    tls_secret = MUTANDAE / "postgres-tls-secret.yaml"
    require(tls_secret, "PG_TLS_CA_KEY")
    require(tls_secret, "PG_TLS_CERT")
    require(tls_secret, "PG_TLS_KEY")
    ca_config = MUTANDAE / "postgres-ca.yaml"
    require(ca_config, "name: mutandae-postgres-ca")
    require(ca_config, "mutandae-postgres.mutandae.svc.cluster.local")
    postgres_tls = MUTANDAE / "postgres.yaml"
    require(postgres_tls, "PG_TLS_CERT")
    require(postgres_tls, "PG_TLS_KEY")
    if "PG_TLS_CA_KEY" in postgres_tls.read_text(encoding="utf-8"):
        raise SystemExit(f"{postgres_tls}: CA signing key must never be mounted into the PostgreSQL Pod")
    policy = MUTANDAE / "network-policy.yaml"
    require(policy, "name: mutandae-default-deny")
    require(policy, "app.kubernetes.io/name: mutandae-postgres")
    require(policy, "port: 5432")
    require(MUTANDAE / "network-policy-postgres.yaml", "name: mutandae-postgres-traffic")
    require(MUTANDAE / "network-policy-postgres.yaml", "port: 5432")
    dex = DEX / "helmrelease.yaml"
    for fragment in (
        "issuer: https://dashboard.belacca.com/oauth2", "id: mutandae",
        "https://mutandae.com/auth/callback", "https://preview.mutandae.com/auth/callback",
        "name: mutandae-dex-client-secret",
    ):
        require(dex, fragment)
    print("validated Mutandae PostgreSQL/RLS, SOPS, document PVC, Dex OIDC, and network contracts")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Mutandae validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
