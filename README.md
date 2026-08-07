# belacca.com GitOps platform

This repository is the cluster-level source of truth for the **old production**
platform: the existing `k3d-pong` Kubernetes cluster, reconciled from
`clusters/vmi3474918/` and publicly addressed at `169.58.97.73`.

## Deployment vocabulary

Use these terms explicitly in issues, runbooks, and incident notes:

- **Old production** means `k3d-pong`, the GitOps tree at
  `clusters/vmi3474918/`, and the public address `169.58.97.73`. The portfolio,
  Pong, analytics, operator routes, Traefik, Flux, and their protected state
  described below belong to this environment.
- **Native staging** means the separate tree at `clusters/belacca-production/`
  for three native servers. The documented native server addresses include
  the native server addresses `169.58.143.41` and `169.58.143.42`; they are not the old production address.
  Native staging currently contains the cluster foundation plus manually staged
  Traefik only. It does not contain deployed portfolio, Pong, analytics, SSO,
  observability, or other native application workloads.
- **Native cutover** is **not started**. Native staging is not an alternate
  old production public endpoint, and no old production rollback command should be
  run against it.

The old production site inventory, redirect aliases, operator surfaces, DNS
records, and monitoring boundaries are maintained in [`docs/SITES.md`](docs/SITES.md).
The canonical portfolio URL is `https://francesco.belacca.com/`;
`belacca.com`, `www.belacca.com`, and `www.francesco.belacca.com` permanently
redirect to it. The canonical Pong URL is `https://pong.belacca.com/`. Pong
currently serves its public real-time journey through the WebSocket-compatible
path. Pong application-native WebTransport support is implemented but remains opt-in
until old production has a reviewed UDP-capable public service, TLS configuration, and
matching network policy.

## Repository map

The following application and platform entries describe **old production**.

| Repository | Runtime | Public host | Flux path in old production |
|---|---|---|---|
| [`cloudnativepong`](https://github.com/macel94/cloudnativepong) | Go lobby, Caddy gateway, Distroless rooms, WebSocket fallback, opt-in WebTransport | [pong.belacca.com](https://pong.belacca.com) | `./k8s/overlays/server` |
| [`francesco-belacca-site`](https://github.com/macel94/francesco-belacca-site) | Static Caddy portfolio | [francesco.belacca.com](https://francesco.belacca.com) | `./deploy` |
| GoatCounter | Self-hosted, cookie-free analytics | [stats.belacca.com](https://stats.belacca.com) | `./clusters/vmi3474918/analytics` |

Native staging has no corresponding application Flux paths yet. Its encrypted
Secret interfaces must not be read as evidence that those applications are
deployed.

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

The existing old production `k3d-pong` cluster, Flux controllers, and Traefik
ACME PVC are retained. Pong's SQLite PVC is managed by the child application
Kustomization, protected with `kustomize.toolkit.fluxcd.io/prune: disabled`,
and its underlying PV uses a `Retain` reclaim policy. This repository does not
recreate the old production cluster and must not be used with destructive `k3d
cluster delete` or PVC deletion commands.

Native staging is separate from this layout. Its current scope is the Flux
foundation, encrypted Secret interfaces/namespaces, Longhorn foundation, and
manually staged Traefik. It has no native application routing or deployed
application workloads.

The GHCR package for `francesco-belacca-site` is anonymously pullable, like the
existing old production Pong packages. GoatCounter uses the pinned public
`arp242/goatcounter` image and stores its data on the old production analytics
PVC. If a future project uses a private package, configure an imagePullSecret
rather than relying on anonymous pulls.

## DNS for old production

The complete supported old production DNS record set is maintained in
[`docs/SITES.md`](docs/SITES.md). Create those DNS-only records at the DNS
provider before expecting normal HTTPS traffic in old production. Traefik uses
the committed Cloudflare DNS-01 challenge configuration. The out-of-band
`kube-system/traefik-cloudflare` Secret must provide
`CLOUDFLARE_DNS_API_TOKEN`; no DNS/API credential is stored in Git. Public DNS
must point each old production hostname at `169.58.97.73`, and public port 443
must reach old production Traefik. DNS-01 proves control of the zone with a TXT
record and does not depend on the HTTP redirect or port 80 for certificate
issuance.

Native staging has no supported public DNS records or application certificate
claim. Do not point the old production hostnames at `.41` or `.42` as part of
native staging; native cutover is not started.

For the complete, repeatable old production procedure—including Cloudflare
token handling, DNS propagation, route ownership, ACME recovery, and rollback—see
[`SUBDOMAIN-RUNBOOK.md`](SUBDOMAIN-RUNBOOK.md).

## Old production delivery flow

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

Native staging is not part of this application delivery flow. Its foundation
and manually staged Traefik must not be described as a native application
deployment.

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

The following commands are explicitly for old production, not native staging:

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

Native staging does not have these old production application/operator routes;
its encrypted Secret interfaces do not mean Dex, Headlamp, Flux Web UI, or
GoatCounter are deployed there.

For a private localhost-only old production alternative, use the existing
port-forward and short-lived Kubernetes token procedure documented in
`cloudnativepong/README.md` and `DEPLOYMENT.md`.
