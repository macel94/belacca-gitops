# Mutandae intake migration and storage contract

## Ownership and target

The application source/image remains owned by `macel94/mutandae`. PostgreSQL,
Longhorn PVCs, SOPS Secrets, Dex static client, NetworkPolicies, and namespace
resources are owned by this `belacca-gitops` repository. The target is the
existing self-hosted `belacca-native` cluster; no AWS/Azure/GCP database or
object-storage service is used.

Follow the parent `belacca-platform/docs/gitops-delivery.md` runbook. Keep the
existing Redis/Vault workloads during the transition. First reconcile Postgres,
PVCs, secret resources, and policies; then publish/promote the new app image and
verify the migration initContainers and intake runtime; only after that remove
legacy Redis/Vault resources in a separately reviewed GitOps change.

## PostgreSQL roles and isolation

`clusters/belacca-production/mutandae/postgres.yaml` deploys the official
PostgreSQL 17.11 Alpine image pinned by digest. Its `PGDATA` is a `pgdata`
subdirectory of the Longhorn mount so the volume's `lost+found` entry does not
break `initdb`. It uses Longhorn-backed RWO storage and creates
`mutandae_live` and `mutandae_preview`, each owned by a
distinct non-superuser `mutandae_{live,preview}_owner` role. Each database has a
distinct `mutandae_{live,preview}_app` runtime login. Both roles are
`NOSUPERUSER NOBYPASSRLS`; public `CONNECT` is revoked and each runtime login
can connect only to its own stage database.

The app Deployment's migration initContainer receives only the matching
stage-owner password. The HTTP container receives only the matching runtime
password through explicit connection components; it shadows the legacy
`DATABASE_URL` key still present in the older intake Secret. Tenant/admin
operations remain separate CLI-only operations. Do not inject a migration-owner
password or the Postgres superuser password into the HTTP container.

The migration runner enables and forces RLS. Its tenant/principal values are
transaction-local custom PostgreSQL settings and can be set by a holder of the
runtime credential. This is defense in depth for trusted repository code, not
protection against a compromised DB credential or SQL injection. Separate
stage roles prevent cross-environment connections; they do not replace
application tenant authorization. Both live and preview migration/runtime
connections use `sslmode=verify-full` and the `mutandae-postgres-ca` ConfigMap.
The server certificate SAN matches the Postgres Service DNS name. A live TLS
handshake, CA trust, certificate expiry, and rotation rehearsal remain required
before collecting PII.

The bootstrap script runs only when PGDATA is empty. If these resources are
applied to an already-initialized volume, a reviewed database operation must
create the per-stage roles, reset credentials, revoke public CONNECT, and grant
the stage-specific database access before either app is promoted. Updating a
Kubernetes Secret alone never changes an existing PostgreSQL role password.
The internal CA certificate is valid for ten years and the server leaf for one
year. Rotate the leaf well before expiry using the SOPS-protected CA key and
restart the database/app Pods after the updated Secret is reconciled. Rotate
the CA before its expiry as a coordinated trust-bundle change: issue a new CA,
update the public ConfigMap and server certificate, and roll all database
clients together.

## Secrets

All secret values are SOPS-encrypted to the existing GitOps age recipient and
stored as `stringData` ciphertext. Required resources are:

- `mutandae-postgres-credentials`: Postgres bootstrap administrator password;
  not mounted by either app container.
- `mutandae-postgres-tls`: SOPS-encrypted Postgres server certificate/private
  key and CA signing key. Only the server cert/key are projected to the Postgres
  TLS initContainer; the CA private key is not mounted. `mutandae-postgres-ca`
  is a public ConfigMap containing the CA certificate for verify-full clients.
- `mutandae-live-database-credentials` and
  `mutandae-preview-database-credentials`: distinct stage owner/runtime DB
  passwords. Postgres bootstrap consumes all four; each app and migration
  initContainer references only its stage's key.
- `mutandae-intake-live` / `mutandae-intake-preview`: payload AES-256-GCM key,
  separate document encryption and signing keys, Dex client secret, and stable
  cookie-session signing key. Legacy `DATABASE_URL` values are shadowed in the
  Deployments and are not passed to the app process.
- `dex/mutandae-dex-client-secret`: Dex static-client secret shared with the
  intake application.

Never put plaintext values in Git, command arguments, CI logs, or image build
arguments. Do not print local `.env` or SOPS plaintext during validation.

## Authentication and tenant bootstrap

Dex issuer: `https://dashboard.belacca.com/oauth2`; client ID: `mutandae`;
redirects are the live and preview `/auth/callback` URLs. Dex's default global
OIDC role is not tenant authority. The app resolves the verified OIDC subject
against PostgreSQL membership for every tenant operation. `/api/v1/me` and the
signed-in landing page reveal the caller's own `sub` with `no-store`; use that
stable value for an owner membership.

No customer tenant is pre-created by GitOps. An authorized operator must use
the documented `mutandae tenant create`/`tenant grant` admin operation with a
stage-appropriate owner connection kept out of the HTTP Pod. The API path tenant
ID is never proof of membership.

## Storage and release gate

Document payloads are application-encrypted before writing to distinct
Longhorn PVCs (`mutandae-live-documents`, `mutandae-preview-documents`). These
PVCs are not a backup. **Do not collect customer PII until a database and
document restore rehearsal, key recovery/rotation procedure, storage health
policy, retention schedule, and incident-response owner are recorded and
verified.** Longhorn persistence alone is not a backup/DR claim.

The migration initContainer and application share an image digest but use
separate stage-specific DB roles and credentials. Verify the generated image
promotion commit, Flux source and Kustomization revisions, PostgreSQL readiness,
both intake Deployments, image digest, health/build marker, Dex sign-in, tenant
isolation, and the signed-file flow before calling the intake site deployed.
