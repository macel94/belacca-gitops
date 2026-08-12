# Native production reliability metadata and runbook index

This repository describes the current reliability contract for **native
production**. Native production is the three-server k3s cluster, reconciled
from `clusters/belacca-production/` and publicly addressed through
`169.58.143.41`, `169.58.143.42`, and `169.58.97.73`. The catalog in
[`../catalog/services.json`](../catalog/services.json) is the machine-readable
source for service owners, hosts, tier, dependencies, SLO intent, RTO, RPO,
dashboard, and runbook references. It is validated in CI with
`scripts/validate-catalog.py`. The former `.73` k3d runtime is retired.

The SLOs below are **proposed**, not measured. Each public service targets
**99% availability over 30 days**, with **no SLA**. The native Prometheus child
provides private diagnostic signals, but no internal metric is the external
availability SLI and the status Git repository is not scraped into Prometheus.
Durable external measurement remains a follow-up capability. A controlled
recovery drill P95 under six minutes is a separate recovery objective and must
not be included in availability arithmetic. The failure drills are in
[`GAME-DAY-DRILLS.md`](GAME-DAY-DRILLS.md), and the backup/object-storage
contract is in [`BACKUP-CONTRACT.md`](BACKUP-CONTRACT.md).
The latter is a names-and-policy contract only: no object store, encryption key,
backup credential, or scheduled backup Job is provisioned here.

## Deployment boundary

- **Native production** is `clusters/belacca-production/` on three native
  servers. The services, SLO proposals, failure domains, and recovery commands
  in this document refer to native production.
- **Retired old production** is the historical `k3d-pong` tree at
  `clusters/vmi3474918/`. It is not a live runtime or rollback target.
- Native production uses direct DNS round-robin on `.73`, `.41`, and `.42`;
  it is not a health-aware load balancer.

## Native production platform boundary and failure domain

- Native production uses three k3s servers and Longhorn replicated storage;
  it still requires a one-writer contract for Pong, GoatCounter, and Dex SQLite.
- Native edge and API DNS are direct round-robin records, not health-aware
  failover. A failed address must be removed manually until a load balancer is
  provisioned.
- Pong, GoatCounter, and Dex use single-writer RWO PVCs. Their replicas remain
  one where they own SQLite; adding replicas without a database design risks
  corruption or inconsistent writes.
- Native production PVCs and Flux inventories are protected by reviewed
  manifests. Do not delete, recreate, or alter protected state as routine
  reconciliation.
- NetworkPolicy enforcement depends on the native production CNI implementing
  the Kubernetes NetworkPolicy API. Rendered policy is not proof of runtime
  enforcement; verify with approved, non-destructive connectivity checks.

Native Longhorn volumes are active production state. Do not mount a SQLite PVC
into a second writer or use ad-hoc restore commands against live data.

## Native production SLO policy

| Service | Initial target | SLI candidate | RTO | RPO |
|---|---:|---|---:|---:|
| Native production portfolio | 99% / 30d | External HTTPS `/health` and homepage success | 4h | N/A |
| Native production Pong | 99% / 30d | External `/api/rooms` plus create/join/WebSocket-compatible real-time synthetic success | 4h | 24h target, manual backup |
| Native production analytics | 99% / 30d | External `/status` plus same-origin `/count` success | 4h | 24h target, manual backup |
| Native production dashboard | 99% / 30d | Proposed authenticated external HTTPS probe | 4h | GitOps is versioned; OAuth Secret is operator-managed |

Before paging on a native production target, install a measurement source and
define the event classification, probe locations, aggregation window, and
burn-rate policy. The desired alert flow is: SLI measurement → SLO/error budget
→ actionable burn-rate alert → incident evidence → tested recovery.

## Native production portfolio

**Symptoms:** `https://francesco.belacca.com/health` fails, the homepage is not
served, or one of the native production portfolio aliases redirects incorrectly.
The supported native production host and alias list is in [`SITES.md`](SITES.md).

1. Confirm the native production context and check DNS and the Traefik
   certificate/Ingress: `kubectl -n portfolio get ingress,svc,pods`.
2. Check `kubectl -n flux-system get kustomization portfolio` and the source
   revision. Do not manually replace the image tag.
3. Check `kubectl -n portfolio logs deploy/francesco-site` for a serving fault.
4. If the workload is unhealthy, roll back the application repository's
   immutable image/tag commit and reconcile the native production child
   Kustomization.
5. Verify `belacca.com`, `www.belacca.com`, and
   `www.francesco.belacca.com` return a permanent redirect to the canonical
   native production portfolio origin while preserving the request path.
6. The service is stateless; do not create or delete a PVC as recovery.

The portfolio's `/count` endpoint depends on the native production in-cluster
GoatCounter Service. An analytics failure should not be treated as a portfolio
image failure without checking the separate native production analytics SLO.

## Native production Pong

**Symptoms:** the native production lobby cannot list/create/join rooms, or the
WebSocket-compatible real-time session fails. Application-native WebTransport
is an optional UDP path and should only be investigated when its separate
native production public service and TLS configuration are enabled.

1. Check native production routing and the gateway:
   `kubectl -n pong get ingress,svc,pods`.
2. Check `kubectl -n flux-system get kustomization pong` and recent events.
3. Check native production API and gateway logs without copying room names, player
   data, tokens, or client addresses into an incident report.
4. Check the protected native production `pong-api-data` PVC and the `pong-api`
   pod. Do not delete the PVC or change its reclaim behavior.
5. For a failed dynamic room, inspect only the relevant Pod/Service and let the
   lobby reconciliation/cleanup path remove terminal or orphan resources.
6. Roll back the application image tag through the Pong repository, then
   reconcile the native production child. Do not hand-edit a live Pod as a
   permanent fix.

The native production room Pod network path is intentionally not fully
default-denied here: its creation is dynamic and its callback/WebSocket
dependencies require an explicit application contract. Application-native
WebTransport is not publicly exposed by the default native production manifests;
enabling it requires a separately reviewed UDP service, TLS material, and
policy rule. The native production policy file documents the parts that are
isolated.

## Native production analytics

**Symptoms:** native production `/status` fails, `/count` returns errors, or the
analytics dashboard cannot load.

1. Check `kubectl -n analytics get statefulset,pod,svc,pvc,helmrelease` in native production.
2. Check that the out-of-band `goatcounter-admin` and `analytics-dex-oauth`
   Secrets exist; never put their passwords, client secrets, or cookie values in
   Git or logs.
3. Check the protected native production `goatcounter-data` PVC and node
   placement. SQLite is single-writer; do not scale the StatefulSet beyond one
   replica.
4. Use the native production manual consistent backup procedure in
   [`../clusters/belacca-production/README.md`](../clusters/belacca-production/README.md) before
   upgrades or storage work.
5. Restore only in an isolated, approved procedure. Verify native production
   `/status`, the public same-origin `/count`, the Dex-protected dashboard
   redirect, and both the Google/Dex gate and the GoatCounter application login
   before considering the incident recovered.

## Native production dashboard

**Symptoms:** native production OAuth redirect/login fails or Headlamp is
unavailable.

1. Check `kubectl -n headlamp get helmrelease,pods,svc` and the
   `headlamp-dex-oauth` Secret's presence without printing values.
2. Verify native production Dex is Ready at the path-scoped issuer
   `https://dashboard.belacca.com/oauth2`, the Google connector callback remains
   exactly `https://dashboard.belacca.com/oauth2/callback`, and Headlamp's
   proxy callback is `https://dashboard.belacca.com/headlamp-auth/callback`.
3. Check that the native production Headlamp HelmRelease renders
   `-proxy-auth=true` and `unsafeUseServiceAccountToken: true`; the former
   consumes trusted OAuth2 Proxy identity headers and the latter supplies the
   shared backend API identity.
4. Check native production Traefik's `dashboard.belacca.com` and
   `dex.belacca.com` Ingresses and certificates.
5. Headlamp's fixed native-production `headlamp` ServiceAccount is bound to the
   built-in `cluster-admin` ClusterRole, so authenticated dashboard access is
   shared-admin, not read-only. The exact Dex/OAuth2 Proxy allowlist is the
   front-door authentication gate; it does not provide per-user Kubernetes RBAC
   or impersonation. Do not expose its ClusterIP, trust client-supplied identity
   headers, or weaken the network policy.
6. If native production OAuth is unavailable, use the documented private
   port-forward/token procedure rather than weakening the public route.

## Incident: dashboard OAuth redirect loop (2026-08-11)

**Observed live evidence:** both native dashboard VIPs (`169.58.143.41` and
`169.58.143.42`) returned `302` from `/` and `/headlamp-auth/start` to an
OAuth2 Proxy authorization URL whose `redirect_uri` was
`https://dashboard.belacca.com/headlamp-auth/callback`. `/headlamp-auth/auth`
returned `401`, while `/headlamp-auth/callback` returned `500`. Flux remained
`200` at `/`, and `/oauth2/callback` returned `303 Location: /`.

**Root cause and fix:** the dashboard Headlamp Ingress is a `/` catch-all and
was also receiving the path-scoped Dex issuer at `/oauth2`. OAuth2 Proxy's
issuer was therefore routed back through itself, producing a self-referential
login loop. The Dex `/oauth2` Ingresses now have explicit Traefik priority 200,
above the Headlamp catch-all. Flux's intended configuration was already
correct: its base URL is `https://flux.belacca.com`, its Dex issuer is
`https://dashboard.belacca.com/oauth2`, and its callback is
`https://flux.belacca.com/oauth2/callback` (owned by the Flux Web chart).

**Expected behavior:** dashboard `/` challenges once via `/headlamp-auth` and
Dex is served only under `/oauth2`; after authentication the callback is
`/headlamp-auth/callback` and the user returns to the requested dashboard
path. Flux challenges via its own OAuth2 flow and returns to
`https://flux.belacca.com/` after `/oauth2/callback`.

**Verification, deploy, and rollback:** render
`kubectl kustomize clusters/belacca-production`, reconcile the native
Kustomizations, and curl both VIPs/hosts. Confirm `/oauth2/.well-known/openid-configuration`
is Dex (not an OAuth2 Proxy 302), dashboard `/` is a single challenge, and
Flux remains 200. Roll back by reverting the focused GitOps commit and
reconciling; do not edit OAuth secrets or weaken the allowlist.

## Incident: dashboard login "invalid_grant" after allowed "Grant Access" (2026-08-11)

**Observed live evidence (UTC):** Dex logged `login successful
connector_id=google username="Francesco Belacca"` and then, ~0.7s later,
`failed to authenticate err="google: failed to get token: oauth2:
\"invalid_grant\" \"Bad Request\""` for every dashboard login attempt at
19:07 and 19:08. The OAuth2 Proxy access log showed no `/headlamp-auth/callback`
arrival for those attempts, so the user's tab rendered Dex's error page instead
of completing the callback. A later attempt (19:19) reached the OAuth2 Proxy
callback but failed with `could not verify id_token ... fetching keys context
canceled`; the next attempt (19:20) completed successfully. The auth requests
for the failed pairs remained in Dex SQLite with `force_approval_prompt=1`,
confirming that `approval_prompt=force` was present and that Dex's code response
had not been finalized.

**Root cause and fix:** oauth2-proxy v7.15.3 defaults `--approval-prompt` to
`force` (`pkg/apis/options/legacy_options.go`), so every authorization URL for
Dex carried `approval_prompt=force`. Dex records `force_approval_prompt=1`, which
overrides `oauth2.skipApprovalScreen: true` (server handles render the explicit
"Grant Access" approval page) and forwards the forced-consent behavior into the
Google flow. On the login page the browser then replayed the same Google callback
URL within ~1s; the first redemption succeeded and the replay raced Dex and
failed with Google `invalid_grant`, and the error page replaced the in-flight
successful redirect chain. Fix: both native OAuth2 Proxy HelmReleases
(dashboard Headlamp and analytics) now set `approval-prompt: auto`; oauth2-proxy
appends `approval_prompt=auto` instead of `force` (an empty value re-enters its
legacy `force` default), Dex only forces the approval screen when the value is
exactly `force` (server/oauth2.go: `ForceApprovalPrompt: q.Get("approval_prompt") == "force"`),
so `skipApprovalScreen: true` is honored and login completes in a single clean
callback.

**Expected behavior:** dashboard `/` challenges once, Google redirection
returns directly to `https://dashboard.belacca.com/oauth2/callback` without a
forced consent/approval page, Dex skips its own approval screen, and the user
lands on the requested dashboard path with one `/headlamp-auth/callback`
exchange. `stats.belacca.com` follows the same contract.

**Verification, deploy, and rollback:** render
`kubectl kustomize clusters/belacca-production`, reconcile the native
Kustomizations, and confirm the rendered OAuth2 Proxy args contain
`--approval-prompt=auto`. Verify `curl -sI https://dashboard.belacca.com/` returns
302 to `/oauth2/auth` **with** `approval_prompt=auto` (never `force`), then
complete one fresh login. Check Dex logs for a single `login successful` with no
following `invalid_grant`. Roll back by reverting this GitOps commit and
reconciling; do not edit OAuth secrets or weaken the allowlist.

## Native production image provenance and vulnerability enforcement

Native production image admission is now fail-closed for Pods in the native
production namespaces. Flux reconciles Kyverno first through
`native-policy-system`, then reconciles the `native-image-policy` Kustomization;
application and platform children depend on that policy gate. The digest rule
rejects tags without a complete `@sha256:` digest. First-party Pong and
portfolio images additionally require matching GitHub Actions keyless SLSA
provenance, CycloneDX SBOM, and vulnerability-decision attestations. Fixed
HIGH/CRITICAL and all known-unfixed findings block; only NONE/LOW/MEDIUM with a
signed `native-production-v1` decision may pass. See
[`IMAGE-PROVENANCE-POLICY.md`](IMAGE-PROVENANCE-POLICY.md) for the exception
process and exact publisher follow-up.

This branch has no production kubeconfig or registry credentials, so it records
policy and offline negative-test evidence only; it does not claim a live
admission attempt. Before rollout, operators must verify Kyverno webhook health,
reconcile both policy Kustomizations, and record a redacted rejected admission
for an invalid test Pod. Until the application publisher workflows emit the
required signed vulnerability decision, their first-party images are correctly
blocked rather than promoted.

## Native production Flux and notifications

1. Check `flux get sources git -A` and `flux get kustomizations -A`, or the
   equivalent native production `kubectl` resources.
2. Inspect the affected native production Kustomization's conditions and events
   before changing source paths or pruning settings.
3. `platform-errors` and `platform-deployments` are defined in the native
   production notification contract under `clusters/belacca-production/`.
   The provider requires the operator-owned Secret described in
   [`NOTIFICATIONS.md`](NOTIFICATIONS.md).
4. If the native production notification receiver is down, continue incident
   response from Flux status/events and do not repeatedly force reconciliation.
5. Never enable native production root pruning or delete protected state as an
   incident shortcut.

Native production has no native production application alert, SLO, or notification
claim. Its foundation must not be reported as native production reliability coverage.

## Native production safe rollback and recovery rules

For a complete native production operator sequence, use
[`GAME-DAY-DRILLS.md`](GAME-DAY-DRILLS.md). For SQLite artifact verification
and the isolated restore rehearsal, use
`cloudnativepong/scripts/backup-restore.sh` and
`cloudnativepong/scripts/restore-rehearsal.sh` from the application checkout.
The rehearsal requires an explicitly acknowledged, newly named
`pong-restore-*` cluster and a pre-existing copied backup; it does not connect
to or mutate native production `belacca-native`.

- Revert native production GitOps/application commits and reconcile the owning native production Flux Kustomization.
- Do not delete/recreate native production `belacca-native`.
- Do not delete native production `pong-api-data`, `goatcounter-data`, or
  `traefik-acme`.
- Do not commit backups, OAuth credentials, analytics passwords, Cloudflare
  tokens, or notification destinations.
- Record native production command output with secrets and private telemetry
  redacted.
- Do not use native production as an ad-hoc restore target or overwrite live
  production PVCs; use an isolated copied-artifact rehearsal.
