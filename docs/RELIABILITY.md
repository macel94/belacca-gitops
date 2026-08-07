# Old production reliability metadata and runbook index

This repository describes the initial reliability contract for **old
production**. Old production is the existing `k3d-pong` cluster, reconciled
from `clusters/vmi3474918/` and publicly addressed at `169.58.97.73`. The
catalog in [`../catalog/services.json`](../catalog/services.json) is the
machine-readable source for old production owners, hosts, tier, dependencies,
SLO intent, RTO, RPO, dashboard, and runbook references. It is validated in CI
with `scripts/validate-catalog.py`.

The SLOs below are **proposed**, not measured. No Prometheus or external
synthetic system is committed here, so the target percentages must not be
reported as achieved availability. Measurement is a follow-up capability. The
failure drills are in [`GAME-DAY-DRILLS.md`](GAME-DAY-DRILLS.md), and the
backup/object-storage contract is in [`BACKUP-CONTRACT.md`](BACKUP-CONTRACT.md).
The latter is a names-and-policy contract only: no object store, encryption key,
backup credential, or scheduled backup Job is provisioned here.

## Deployment boundary

- **Old production** is `k3d-pong` / `clusters/vmi3474918/` / `169.58.97.73`.
  The services, SLO proposals, failure domains, and recovery commands in this
document refer to old production.
- **Native staging** is `clusters/belacca-production/` on three native servers,
  including `169.58.143.41` and `169.58.143.42`. It currently contains the
  foundation plus manually staged Traefik only; no native application,
  Headlamp, or observability workload is deployed.
- **Native cutover is not started.** Native staging is outside the old production SLO, RTO, RPO, monitoring, and
  rollback claims.

## Old production platform boundary and failure domain

- Old production is the existing `k3d-pong` installation on one physical host
  with three k3d nodes. The nodes provide scheduling placement, but they do not
  create an independent host failure domain.
- Old production `local-path` PVCs are node-local. A node or host failure can
  make the data unavailable until the node/storage is recovered or an operator
  restores a backup elsewhere.
- Old production Pong and GoatCounter use single-writer SQLite PVCs. Their
  Stateful/Deployment replicas are intentionally one where they own the
  database; adding replicas without a database design would risk corruption or
  inconsistent writes.
- `pong-api-data`, `goatcounter-data`, and the old production Traefik ACME claim
  are protected from Flux pruning. Do not delete, recreate, or alter their
  protected behavior as part of routine reconciliation.
- The old production Flux root is `prune: true` after the migration and
  ownership verification in [`../MIGRATION.md`](../MIGRATION.md). The old
  old production application/analytics/ACME stateful claims and relevant
  Namespaces remain explicitly prune-protected.
- NetworkPolicy enforcement depends on the old production cluster CNI
  implementing the Kubernetes NetworkPolicy API. Rendered policy is not proof
  of runtime enforcement; verify with approved, non-destructive connectivity
  checks after reconciliation.

Native staging Longhorn and the native foundation are not evidence of old
production storage migration or native application readiness. Do not restore an
old production database into native staging as part of routine verification.

## Old production SLO policy

| Service | Initial target | SLI candidate | RTO | RPO |
|---|---:|---|---:|---:|
| Old production portfolio | 99.5% / 30d | External HTTPS `/health` and homepage success | 4h | N/A |
| Old production Pong | 99.5% / 30d | `/api/rooms` plus create/join/WebSocket-compatible real-time synthetic success | 4h | 24h target, manual backup |
| Old production analytics | 99.0% / 30d | `/status` plus same-origin `/count` success | 4h | 24h target, manual backup |
| Old production dashboard | 99.0% / 30d | Authenticated HTTPS probe | 4h | GitOps is versioned; OAuth Secret is operator-managed |

Before paging on an old production target, install a measurement source and
define the event classification, probe locations, aggregation window, and
burn-rate policy. The desired alert flow is: SLI measurement → SLO/error budget
→ actionable burn-rate alert → incident evidence → tested recovery.

## Old production portfolio

**Symptoms:** `https://francesco.belacca.com/health` fails, the homepage is not
served, or one of the old production portfolio aliases redirects incorrectly.
The supported old production host and alias list is in [`SITES.md`](SITES.md).

1. Confirm the old production context and check DNS and the Traefik
   certificate/Ingress: `kubectl -n portfolio get ingress,svc,pods`.
2. Check `kubectl -n flux-system get kustomization portfolio` and the source
   revision. Do not manually replace the image tag.
3. Check `kubectl -n portfolio logs deploy/francesco-site` for a serving fault.
4. If the workload is unhealthy, roll back the application repository's
   immutable image/tag commit and reconcile the old production child
   Kustomization.
5. Verify `belacca.com`, `www.belacca.com`, and
   `www.francesco.belacca.com` return a permanent redirect to the canonical old
   old production portfolio origin while preserving the request path.
6. The service is stateless; do not create or delete a PVC as recovery.

The portfolio's `/count` endpoint depends on the old production in-cluster
GoatCounter Service. An analytics failure should not be treated as a portfolio
image failure without checking the separate old production analytics SLO.

## Old production Pong

**Symptoms:** the old production lobby cannot list/create/join rooms, or the
WebSocket-compatible real-time session fails. Application-native WebTransport
is an optional UDP path and should only be investigated when its separate old
old production public service and TLS configuration are enabled.

1. Check old production routing and the gateway:
   `kubectl -n pong get ingress,svc,pods`.
2. Check `kubectl -n flux-system get kustomization pong` and recent events.
3. Check old production API and gateway logs without copying room names, player
   data, tokens, or client addresses into an incident report.
4. Check the protected old production `pong-api-data` PVC and the `pong-api`
   pod. Do not delete the PVC or change its reclaim behavior.
5. For a failed dynamic room, inspect only the relevant Pod/Service and let the
   lobby reconciliation/cleanup path remove terminal or orphan resources.
6. Roll back the application image tag through the Pong repository, then
   reconcile the old production child. Do not hand-edit a live Pod as a
   permanent fix.

The old production room Pod network path is intentionally not fully
default-denied here: its creation is dynamic and its callback/WebSocket
dependencies require an explicit application contract. Application-native
WebTransport is not publicly exposed by the default old production manifests;
enabling it requires a separately reviewed UDP service, TLS material, and
policy rule. The old production policy file documents the parts that are
isolated.

## Old production analytics

**Symptoms:** old production `/status` fails, `/count` returns errors, or the
analytics dashboard cannot load.

1. Check `kubectl -n analytics get statefulset,pod,svc,pvc,helmrelease` in old
   old production.
2. Check that the out-of-band `goatcounter-admin` and `analytics-dex-oauth`
   Secrets exist; never put their passwords, client secrets, or cookie values in
   Git or logs.
3. Check the protected old production `goatcounter-data` PVC and node
   placement. SQLite is single-writer; do not scale the StatefulSet beyond one
   replica.
4. Use the old production manual consistent backup procedure in
   [`../clusters/vmi3474918/README.md`](../clusters/vmi3474918/README.md) before
   upgrades or storage work.
5. Restore only in an isolated, approved procedure. Verify old production
   `/status`, the public same-origin `/count`, the Dex-protected dashboard
   redirect, and both the Google/Dex gate and the GoatCounter application login
   before considering the incident recovered.

## Old production dashboard

**Symptoms:** old production OAuth redirect/login fails or Headlamp is
unavailable.

1. Check `kubectl -n headlamp get helmrelease,pods,svc` and the
   `headlamp-dex-oauth` Secret's presence without printing values.
2. Verify old production Dex is Ready at the path-scoped issuer
   `https://dashboard.belacca.com/oauth2`, the Google connector callback remains
   exactly `https://dashboard.belacca.com/oauth2/callback`, and Headlamp's
   proxy callback is `https://dashboard.belacca.com/headlamp-auth/callback`.
3. Check that the old production Headlamp HelmRelease renders
   `-proxy-auth=true` and `unsafeUseServiceAccountToken: true`; the former
   consumes trusted OAuth2 Proxy identity headers and the latter supplies the
   shared backend API identity.
4. Check old production Traefik's `dashboard.belacca.com` and
   `dex.belacca.com` Ingresses and certificates.
5. Headlamp's fixed old-production `headlamp` ServiceAccount is bound to the
   built-in `cluster-admin` ClusterRole, so authenticated dashboard access is
   shared-admin, not read-only. The exact Dex/OAuth2 Proxy allowlist is the
   front-door authentication gate; it does not provide per-user Kubernetes RBAC
   or impersonation. Do not expose its ClusterIP, trust client-supplied identity
   headers, or weaken the network policy.
6. If old production OAuth is unavailable, use the documented private
   port-forward/token procedure rather than weakening the public route.

## Old production Flux and notifications

1. Check `flux get sources git -A` and `flux get kustomizations -A`, or the
   equivalent old production `kubectl` resources.
2. Inspect the affected old production Kustomization's conditions and events
   before changing source paths or pruning settings.
3. `platform-errors` and `platform-deployments` are defined in the old
   old production [`../clusters/vmi3474918/notifications.yaml`](../clusters/vmi3474918/notifications.yaml).
   The provider requires the operator-owned Secret described in
   [`NOTIFICATIONS.md`](NOTIFICATIONS.md).
4. If the old production notification receiver is down, continue incident
   response from Flux status/events and do not repeatedly force reconciliation.
5. Never enable old production root pruning or delete protected state as an
   incident shortcut.

Native staging has no old production application alert, SLO, or notification
claim. Its foundation must not be reported as native staging reliability coverage.

## Old production safe rollback and recovery rules

For a complete old production operator sequence, use
[`GAME-DAY-DRILLS.md`](GAME-DAY-DRILLS.md). For SQLite artifact verification
and the isolated restore rehearsal, use
`cloudnativepong/scripts/backup-restore.sh` and
`cloudnativepong/scripts/restore-rehearsal.sh` from the application checkout.
The rehearsal requires an explicitly acknowledged, newly named
`pong-restore-*` cluster and a pre-existing copied backup; it does not connect
to or mutate old production `k3d-pong`.

- Revert old production GitOps/application commits and reconcile the owning old
  old production Flux Kustomization.
- Do not delete/recreate old production `k3d-pong`.
- Do not delete old production `pong-api-data`, `goatcounter-data`, or
  `traefik-acme`.
- Do not commit backups, OAuth credentials, analytics passwords, Cloudflare
  tokens, or notification destinations.
- Record old production command output with secrets and private telemetry
  redacted.
- Do not describe native staging as a restore target or use it for an old
  production rollback until a future native cutover is separately approved.
