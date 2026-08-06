# Reliability metadata and runbook index

This repository describes the platform's initial reliability contract. The
catalog in [`../catalog/services.json`](../catalog/services.json) is the
machine-readable source for owners, hosts, tier, dependencies, SLO intent, RTO,
RPO, dashboard, and runbook references. It is validated in CI with
`scripts/validate-catalog.py`.

The SLOs below are **proposed**, not measured. No Prometheus or external
synthetic system is committed here, so the target percentages must not be
reported as achieved availability. Measurement is a follow-up capability.
The failure drills are in [`GAME-DAY-DRILLS.md`](GAME-DAY-DRILLS.md), and the
backup/object-storage contract is in [`BACKUP-CONTRACT.md`](BACKUP-CONTRACT.md).
The latter is a names-and-policy contract only: no object store, encryption key,
backup credential, or scheduled backup Job is provisioned here.

## Platform boundary and failure domain

- The cluster is the existing `k3d-pong` installation on one physical host
  with three k3d nodes. The nodes provide scheduling placement, but they do not
  create an independent host failure domain.
- `local-path` PVCs are node-local. A node or host failure can make the data
  unavailable until the node/storage is recovered or an operator restores a
  backup elsewhere.
- Pong and GoatCounter use single-writer SQLite PVCs. Their Stateful/Deployment
  replicas are intentionally one where they own the database; adding replicas
  without a database design would risk corruption or inconsistent writes.
- `pong-api-data`, `goatcounter-data`, and the Traefik ACME claim are protected
  from Flux pruning. Do not delete, recreate, or alter their protected behavior
  as part of routine reconciliation.
- The Flux root is `prune: true` after the migration and ownership verification
  in [`../MIGRATION.md`](../MIGRATION.md). The application/analytics/ACME
  stateful claims and relevant Namespaces remain explicitly prune-protected.
- NetworkPolicy enforcement depends on the cluster CNI implementing the
  Kubernetes NetworkPolicy API. Rendered policy is not proof of runtime
  enforcement; verify with approved, non-destructive connectivity checks after
  reconciliation.

## SLO policy

| Service | Initial target | SLI candidate | RTO | RPO |
|---|---:|---|---:|---:|
| Portfolio | 99.5% / 30d | External HTTPS `/health` and homepage success | 4h | N/A |
| Pong | 99.5% / 30d | `/api/rooms` plus create/join/WebSocket synthetic success | 4h | 24h target, manual backup |
| Analytics | 99.0% / 30d | `/status` plus same-origin `/count` success | 4h | 24h target, manual backup |
| Dashboard | 99.0% / 30d | Authenticated HTTPS probe | 4h | GitOps is versioned; OAuth Secret is operator-managed |

Before paging on a target, install a measurement source and define the event
classification, probe locations, aggregation window, and burn-rate policy.
The desired alert flow is: SLI measurement → SLO/error budget → actionable
burn-rate alert → incident evidence → tested recovery.

## Portfolio

**Symptoms:** `https://francesco.belacca.com/health` fails, homepage is not
served, or the apex redirect is wrong.

1. Check DNS and the Traefik certificate/Ingress:
   `kubectl -n portfolio get ingress,svc,pods`.
2. Check `kubectl -n flux-system get kustomization portfolio` and the source
   revision. Do not manually replace the image tag.
3. Check `kubectl -n portfolio logs deploy/francesco-site` for a serving fault.
4. If the workload is unhealthy, roll back the application repository's
   immutable image/tag commit and reconcile the child Kustomization.
5. The service is stateless; do not create or delete a PVC as recovery.

The portfolio's `/count` endpoint depends on the in-cluster GoatCounter
Service. A GoatCounter failure should not be treated as a portfolio image
failure without checking the separate analytics SLO.

## Pong

**Symptoms:** the lobby cannot list/create/join rooms, or WebSocket sessions
fail.

1. Check routing and the gateway: `kubectl -n pong get ingress,svc,pods`.
2. Check `kubectl -n flux-system get kustomization pong` and recent events.
3. Check API and gateway logs without copying room names, player data, tokens,
   or client addresses into an incident report.
4. Check the protected `pong-api-data` PVC and the `pong-api` pod. Do not delete
   the PVC or change its reclaim behavior.
5. For a failed dynamic room, inspect only the relevant Pod/Service and let the
   lobby reconciliation/cleanup path remove terminal or orphan resources.
6. Roll back the application image tag through the Pong repository, then
   reconcile. Do not hand-edit a live Pod as a permanent fix.

The room Pod network path is intentionally not fully default-denied here: its
creation is dynamic and its callback/WebSocket dependencies require an explicit
application contract. The policy file documents the parts that are isolated.

## Analytics

**Symptoms:** `/status` fails, `/count` returns errors, or the dashboard cannot
load.

1. Check `kubectl -n analytics get statefulset,pod,svc,pvc,helmrelease`.
2. Check that the out-of-band `goatcounter-admin` and `analytics-dex-oauth`
   Secrets exist; never put their passwords, client secrets, or cookie values in
   Git or logs.
3. Check the protected `goatcounter-data` PVC and node placement. SQLite is
   single-writer; do not scale the StatefulSet beyond one replica.
4. Use the manual consistent backup procedure in
   [`../clusters/vmi3474918/README.md`](../clusters/vmi3474918/README.md) before
   upgrades or storage work.
5. Restore only in an isolated, approved procedure. Verify `/status`, the
   public same-origin `/count`, Dex-protected dashboard redirect, and the
   GoatCounter application login before considering the incident recovered.

## Dashboard

**Symptoms:** OAuth redirect/login fails or Headlamp is unavailable.

1. Check `kubectl -n headlamp get helmrelease,pods,svc` and the
   `headlamp-dex-oauth` Secret's presence without printing values.
2. Verify Dex is Ready, the callback remains exactly
   `https://dashboard.belacca.com/oauth2/callback`, and the Google OAuth app
   authorizes `https://dex.belacca.com/callback`.
3. Check Traefik's `dashboard.belacca.com` and `dex.belacca.com` Ingresses and
   certificates.
4. Headlamp's backend ServiceAccount is intentionally admin only behind the
   exact Dex/OAuth2 Proxy allowlist. Do not expose its ClusterIP or weaken the
   network policy.
5. If OAuth is unavailable, use the documented private port-forward/token
   procedure rather than weakening the public route.

## Flux and notifications

1. Check `flux get sources git -A` and `flux get kustomizations -A`, or the
   equivalent `kubectl` resources.
2. Inspect the affected Kustomization's conditions and events before changing
   source paths or pruning settings.
3. `platform-errors` and `platform-deployments` are defined in
   [`../clusters/vmi3474918/notifications.yaml`](../clusters/vmi3474918/notifications.yaml). The provider requires the
   operator-owned Secret described in [`NOTIFICATIONS.md`](NOTIFICATIONS.md).
4. If the notification receiver is down, continue incident response from Flux
   status/events and do not repeatedly force reconciliation.
5. Never enable root pruning or delete protected state as an incident shortcut.

## Safe rollback and recovery rules

For a complete operator sequence, use [`GAME-DAY-DRILLS.md`](GAME-DAY-DRILLS.md).
For SQLite artifact verification and the isolated restore rehearsal, use
`cloudnativepong/scripts/backup-restore.sh` and
`cloudnativepong/scripts/restore-rehearsal.sh` from the application checkout.
The rehearsal requires an explicitly acknowledged, newly named
`pong-restore-*` cluster and a pre-existing copied backup; it does not connect
to or mutate `k3d-pong`.

- Revert GitOps/application commits and reconcile the owning Flux Kustomization.
- Do not delete/recreate the `k3d-pong` cluster.
- Do not delete `pong-api-data`, `goatcounter-data`, or `traefik-acme`.
- Do not commit backups, OAuth credentials, analytics passwords, Cloudflare
  tokens, or notification destinations.
- Record command output with secrets and private telemetry redacted.
