# belacca.com GitOps platform

This repository is the cluster-level source of truth for the **native production**
platform: the three-server k3s cluster at `clusters/belacca-production/`,
publicly served through `169.58.143.41`, `169.58.143.42`, and `169.58.97.73`.

## Deployment vocabulary

Use these terms explicitly in issues, runbooks, and incident notes:

- **Native production** means `clusters/belacca-production/` and the three
  native k3s servers. Flux, Traefik, cert-manager, TLS, Pong, portfolio,
  analytics, Dex, Headlamp, and Flux Web are public-production workloads.
- **Retired old production** means the former `k3d-pong` cluster and its
  historical GitOps tree at `clusters/vmi3474918/`. Its Podman containers were
  removed after the controlled state handoff; its manifests and Git history are
  retained for audit/reference, not live reconciliation.
- Cloudflare DNS-only A records for application hostnames contain `.73`,
  `.41`, and `.42`; `k3s-api.belacca.com` remains `.41` and `.42` only. This
  is direct DNS round-robin, not health-aware failover.
- The native edge uses namespace-local cert-manager TLS Secrets and does not
  mount the retired old-production `acme.json`.

The supported site inventory, current owners, redirect aliases, operator
surfaces, DNS records, and monitoring boundaries are maintained in
[`docs/SITES.md`](docs/SITES.md).
The canonical portfolio URL is `https://francesco.belacca.com/`;
`belacca.com`, `www.belacca.com`, and `www.francesco.belacca.com` permanently
redirect to it while preserving paths. The canonical Pong URL is
`https://pong.belacca.com/`. Pong serves its public real-time journey through the
WebSocket-compatible path. Pong application-native WebTransport remains opt-in
until a reviewed UDP-capable public service, TLS configuration, and matching
network policy exist.

## Repository map

The following application and platform entries describe **old production**.

| Repository | Runtime | Public host | Flux path in old production |
|---|---|---|---|
| [`cloudnativepong`](https://github.com/macel94/cloudnativepong) | Go lobby, Caddy gateway, Distroless rooms, WebSocket fallback, opt-in WebTransport | [pong.belacca.com](https://pong.belacca.com) | `./k8s/overlays/server` |
| [`francesco-belacca-site`](https://github.com/macel94/francesco-belacca-site) | Static Caddy portfolio | [francesco.belacca.com](https://francesco.belacca.com) | `./deploy` |
| GoatCounter | Self-hosted, cookie-free analytics | [stats.belacca.com](https://stats.belacca.com) | `./clusters/vmi3474918/analytics` |

Native production has published application Flux paths for Pong, portfolio,
analytics, Dex, Headlamp, Flux Web, private Prometheus diagnostics, and native
Flux notification contracts. The native root and all child Kustomizations
reconcile successfully. Workloads remain private ClusterIP services behind
native Traefik; public traffic enters through the two direct host-network edges.
The external status repository is the source of the public 99%/30d SLO evidence;
native Prometheus is diagnostic and the notification destination remains out of
band/unprovisioned.

## Why child GitRepositories instead of submodules?

Flux supports Git submodules, but application repositories are represented here
as independent Flux `GitRepository` objects. This keeps each project buildable
and releasable on its own, permits different credentials later if a project
becomes private, and lets changes in each source trigger its own Kustomization.
It also avoids requiring every developer and deployment tool to initialize a
nested checkout.

## Old production cluster layout

```text
Old production: k3d-pong / clusters/vmi3474918 / 169.58.97.73
├── cluster infrastructure
│   ├── Traefik + persistent ACME storage
│   ├── Dex + Google OIDC identity broker
│   ├── Flux Web UI + Dex OIDC
│   └── Headlamp + Dex-backed OAuth2 Proxy (identity-aware, ClusterIP)
├── child source: cloudnativepong ──> Kustomization pong ──> namespace pong
├── child source: francesco-belacca-site ──> Kustomization portfolio
├── child Kustomization: analytics ──> GoatCounter + SQLite PVC
└── host routing
    ├── pong.belacca.com ──> pong-gateway
    ├── francesco.belacca.com ──> francesco-site
    ├── stats.belacca.com ──> GoatCounter analytics
    ├── portfolio aliases ──> HTTPS redirect to portfolio
    ├── dashboard.belacca.com ──> Dex-backed OAuth2 Proxy ──> Headlamp (proxy-auth)
    ├── flux.belacca.com ──> Flux Web UI ──> Dex
    ├── dex.belacca.com ──> Dex ──> Google
    └── www.francesco.belacca.com ──> HTTPS redirect to portfolio
```

The old production `k3d-pong` cluster has been retired after its Pong,
GoatCounter, and Dex SQLite state was quiesced, integrity-checked, and restored
into native Longhorn-backed RWO PVCs. The old `clusters/vmi3474918/` tree,
protected PVC/ACME manifests, and rollback documentation remain historical
reference material. Do not reconcile it as a second public owner.

Native production owns the Flux foundation, encrypted Secret interfaces,
Longhorn, cert-manager DNS-01/TLS, Flux-managed Traefik, native routing, and
Pong/portfolio/Dex/Headlamp/Flux Web/analytics workloads. Stateful SQLite
workloads remain single-writer.

The GHCR package for `francesco-belacca-site` is anonymously pullable, like the
existing old production Pong packages. GoatCounter uses the pinned public
`arp242/goatcounter` image and stores its data on the old production analytics
PVC. If a future project uses a private package, configure an imagePullSecret
rather than relying on anonymous pulls.

## Current native production DNS

Cloudflare DNS-only records for every supported application hostname contain
`169.58.97.73`, `169.58.143.41`, and `169.58.143.42` with short
TTLs; `k3s-api.belacca.com` remains on `169.58.143.41` and `169.58.143.42`.
This direct DNS round-robin has no health-aware withdrawal; operators must
monitor all edges and manually remove an unhealthy address if necessary.
Traefik terminates TLS on all native edges. cert-manager uses Cloudflare
DNS-01 and namespace-local Kubernetes TLS Secrets; the API token remains
out-of-band in the native cluster and is not stored in Git.

The former `.73` application records were removed. The `.73` host remains a
native k3s control-plane member, but the retired k3d application containers no
longer own public ports or DNS.

## Retired old-production delivery flow (historical)

The following section is retained for audit/reference only. Native production
is the current delivery plane and is described above.

The old production platform root at `clusters/vmi3474918/` is set to
`prune: true` after its ownership migration was verified. Its checked-in root
render contains every object in the old production root inventory, child
inventories are disjoint, the application/routing children are Ready, and the
stateful Namespace/PVC resources are explicitly protected from pruning.
Service ownership, SLO intent, RTO/RPO, dependencies, dashboard, and runbook
metadata are recorded in [`catalog/services.json`](catalog/services.json) and
validated in CI. Old production reliability boundaries and response procedures
are in [`docs/RELIABILITY.md`](docs/RELIABILITY.md); operator failure drills
for the gateway, static service, lobby, rooms, Flux, and NetworkPolicy are in
[`docs/GAME-DAY-DRILLS.md`](docs/GAME-DAY-DRILLS.md). The backup retention,
encryption, object-storage, and no-values Secret contract is in
[`docs/BACKUP-CONTRACT.md`](docs/BACKUP-CONTRACT.md); notification Secret
provisioning is in [`docs/NOTIFICATIONS.md`](docs/NOTIFICATIONS.md). The scoped
NetworkPolicies and replicated-workload PDBs are under
`clusters/vmi3474918/policies/`. The staged old production `observability`
child remains at `prune: false` until its own resource, CNI, and target-health
checks pass. See `MIGRATION.md` for the old production incident record and safe
ownership procedure.

Native production is the current application delivery plane. Its published
routed application definitions and Flux-managed Traefik are live public
production resources validated by direct and pinned-edge probes.

Publish and reconcile the old production GitOps commit before relying on old
production root pruning. Flux's old production Kustomization must have pruning
disabled and reconciled before resources are moved to a different
Kustomization; replacing a source and moving its inventory in one commit can
garbage-collect live workloads and PVCs before the new child adopts them.

1. Change an application in its own repository.
2. Its tests run and the image is published to GHCR with an immutable
   `sha-<commit>` tag.
3. The application repository records that tag in its deployment Kustomization.
4. Old production Flux polls the child source every minute and reconciles the
   app every ten minutes. Force it when needed:

   ```bash
   flux reconcile source git flux-system -n flux-system
   flux reconcile source git cloudnativepong -n flux-system
   flux reconcile source git francesco-belacca-site -n flux-system
   flux reconcile kustomization pong -n flux-system --with-source
   flux reconcile kustomization portfolio -n flux-system --with-source
   ```

5. The old production cluster-level routing is changed here, reviewed, and
   reconciled by the old production root Kustomization.

## Old production verification and rollback

The following commands are historical retired-old-production examples, not
native production commands:

```bash
kubectl config use-context k3d-pong
kubectl get nodes
kubectl -n pong get deploy,pods,svc,ingress
kubectl -n portfolio get deploy,pods,svc,ingress
flux get sources git -A
flux get kustomizations -A
curl -fsS https://francesco.belacca.com/health
curl -I https://belacca.com/
curl -I https://www.belacca.com/
curl -I https://www.francesco.belacca.com/
```

To roll back an old production app, revert the deployment-tag commit in that
application repository and reconcile its old production child Kustomization.
To roll back old production routing or policies, revert this repository's
commit and reconcile the old production root Kustomization. The detailed,
scoped commands are in [`docs/GAME-DAY-DRILLS.md`](docs/GAME-DAY-DRILLS.md).
Never remove `pong-api-data`, its PV, or `kube-system/traefik-acme` during an
old production rollback.

Recovery status is intentionally explicit: the application repository has a
local SQLite verification helper and an opt-in isolated `pong-restore-*` k3d
rehearsal. This repository does **not** provision object storage, retention,
encryption keys, backup credentials, or a scheduled backup Job for old
production. Those external prerequisites and the names-only Secret interface
are documented in [`docs/BACKUP-CONTRACT.md`](docs/BACKUP-CONTRACT.md). Do not
commit backup artifacts or values to a repository.

## Old production cluster dashboard

Headlamp is a lightweight CNCF Kubernetes dashboard installed from the pinned
official Helm chart (`0.44.0`) and remains a ClusterIP service in old
production. The public route is old production Traefik → Dex-backed OAuth2
Proxy → Headlamp; OAuth2 Proxy is installed from the pinned official chart
(`10.7.0`). Dex is installed from the pinned official chart (`0.24.1`) with
persistent SQLite state. The Flux Web UI is installed as a standalone Flux
Operator chart (`0.57.0`) without replacing the existing old production Flux
controllers.

The old production dashboard is available at:

```text
https://dashboard.belacca.com/
```

Headlamp uses its official identity-aware proxy mode: OAuth2 Proxy injects
trusted identity headers after the Dex/Google login, and Headlamp uses its
mounted in-cluster ServiceAccount for Kubernetes API calls. The backend is
intentionally a shared administrative identity gated by the single-email proxy
allowlist, not per-user Kubernetes OIDC/RBAC impersonation.

Old production Traefik redirects HTTP to HTTPS and obtains the certificate with
the committed Let's Encrypt DNS-01 resolver. Dex uses the path-scoped issuer
`https://dashboard.belacca.com/oauth2`; its Google callback reuses the existing
authorized URI `https://dashboard.belacca.com/oauth2/callback`. The Headlamp
proxy uses `/headlamp-auth` for its own callback, and the analytics proxy uses
its stats callback. All proxies permit only `belakkuz@gmail.com`;
`dex.belacca.com` remains a redirect alias.

```text
https://dashboard.belacca.com/headlamp-auth/callback
```

The Google OAuth client ID and secret are stored in the out-of-band
`dex-google-oauth` Secret. The existing Google application must retain
`https://dashboard.belacca.com/oauth2/callback`; no new Google Cloud Console
credential is required for the path-scoped Dex issuer. Dex client secrets and
OAuth2 Proxy cookie secrets are stored in the out-of-band
`dex-client-secrets`, `flux-web-client`, `headlamp-dex-oauth`, and
`analytics-dex-oauth` Secrets. None is represented in Git. The Headlamp proxy
allowlist contains only `belakkuz@gmail.com`; Headlamp's identity-aware proxy
mode consumes those trusted headers, while its in-cluster mode uses one backend
ServiceAccount. The separately named `headlamp-authenticated-admin` binding
grants that backend `cluster-admin`. This is shared-admin access rather than
per-user Kubernetes OIDC/RBAC. Keep the public proxy allowlist and the private
ClusterIP/network policy intact.

The previous `headlamp-dashboard-auth` BasicAuth Secret and middleware remain
available as an old production rollback path while OAuth is being validated.
They are not used by the active HTTPS route. The complete shared identity
contract, required Secret keys, Google callback, and GoatCounter limitation are
in [`docs/SSO.md`](docs/SSO.md).

Native production now owns these application/operator routes; its encrypted
Secret interfaces are reconciled with Dex, Headlamp, Flux Web UI, and GoatCounter
workloads in the native cluster.

For a private localhost-only old production alternative, use the existing
port-forward and short-lived Kubernetes token procedure documented in
`cloudnativepong/README.md` and `DEPLOYMENT.md`.
