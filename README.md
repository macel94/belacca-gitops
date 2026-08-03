# belacca.com GitOps platform

This repository is the cluster-level source of truth for hosting multiple
projects under `belacca.com` on the existing `k3d-pong` Kubernetes cluster.

## Repository map

| Repository | Runtime | Public host | Flux path |
|---|---|---|---|
| [`cloudnativepong`](https://github.com/macel94/cloudnativepong) | Go lobby, WebSockets, dynamic room Pods | [pong.belacca.com](https://pong.belacca.com) | `./k8s/overlays/server` |
| [`francesco-belacca-site`](https://github.com/macel94/francesco-belacca-site) | Static NGINX portfolio | [francesco.belacca.com](https://francesco.belacca.com) | `./deploy` |

The apex names `belacca.com` and `www.belacca.com` permanently redirect to the
portfolio. The canonical Pong URL is now the `pong` subdomain.

## Why child GitRepositories instead of submodules?

Flux supports Git submodules, but application repositories are represented here
as independent Flux `GitRepository` objects. This keeps each project buildable
and releasable on its own, permits different credentials later if a project
becomes private, and lets changes in each source trigger its own Kustomization.
It also avoids requiring every developer and deployment tool to initialize a
nested checkout.

## Cluster layout

```text
Flux root source (belacca-gitops)
├── cluster infrastructure
│   ├── Traefik + persistent ACME storage
│   └── Headlamp (private ClusterIP, read-only RBAC)
├── child source: cloudnativepong ──> Kustomization pong ──> namespace pong
├── child source: francesco-belacca-site ──> Kustomization portfolio
└── host routing
    ├── pong.belacca.com ──> pong-gateway
    ├── francesco.belacca.com ──> francesco-site
    └── belacca.com / www ──> HTTPS redirect to portfolio
```

The existing `k3d-pong` cluster, Flux controllers, and Traefik ACME PVC are
retained. Pong's SQLite PVC is managed by the child application Kustomization,
protected with `kustomize.toolkit.fluxcd.io/prune: disabled`, and its underlying
PV uses a `Retain` reclaim policy. This repository does not recreate the cluster
and must not be used with destructive `k3d cluster delete` or PVC deletion
commands.

The GHCR package for `francesco-belacca-site` is anonymously pullable, like the
existing Pong packages. If a future project uses a private package, configure
an imagePullSecret rather than relying on anonymous pulls.

## DNS

Create these A records at the DNS provider before expecting ACME issuance:

```text
pong.belacca.com       A  169.58.97.73
francesco.belacca.com  A  169.58.97.73
```

Keep the existing records for `belacca.com` and `www.belacca.com` pointing at the
same address. Traefik uses the TLS-ALPN-01 challenge, so public port 443 must
reach Traefik for certificate issuance and renewal. Normal HTTP traffic on port
80 redirects to HTTPS.

## Delivery flow

The current platform root intentionally uses `prune: false` while the cutover
is validated. This is a guard, not a substitute for a staged ownership
transfer: Flux's old Kustomization must have pruning disabled and reconciled
before resources are moved to a different Kustomization. Replacing the source
behind one root and moving its inventory in one commit can garbage-collect live
workloads and PVCs before the new child adopts them. See `MIGRATION.md` for the
incident record and safe procedure.

After DNS, routing, workload, and stateful-resource verification, set `prune:
true` in `clusters/vmi3474918/flux-system/gotk-sync.yaml` and commit that
change so the platform root can prune only resources it owns.

1. Change an application in its own repository.
2. Its tests run and the image is published to GHCR with an immutable
   `sha-<commit>` tag.
3. The application repository records that tag in its deployment Kustomization.
4. Flux polls the child source every minute and reconciles the app every ten
   minutes. Force it when needed:

   ```bash
   flux reconcile source git flux-system -n flux-system
   flux reconcile source git cloudnativepong -n flux-system
   flux reconcile source git francesco-belacca-site -n flux-system
   flux reconcile kustomization pong -n flux-system --with-source
   flux reconcile kustomization portfolio -n flux-system --with-source
   ```

5. The cluster-level routing is changed here, reviewed, and reconciled by the
   root Kustomization.

## Verification and rollback

```bash
kubectl config use-context k3d-pong
kubectl get nodes
kubectl -n pong get deploy,pods,svc,ingress
kubectl -n portfolio get deploy,pods,svc,ingress
flux get sources git -A
flux get kustomizations -A
curl -fsS https://francesco.belacca.com/health
curl -I https://belacca.com/
```

To roll back an app, revert the deployment-tag commit in that application
repository and reconcile its child Kustomization. To roll back routing, revert
this repository's routing commit and reconcile the root Kustomization. Never
remove `pong-api-data`, its PV, or `kube-system/traefik-acme` during rollback.
The current Pong database backup created during the cutover is retained on the
cluster host outside Git; do not commit it to a repository.

## Private cluster dashboard

Headlamp remains ClusterIP-only and is not exposed by any public route. Access
it through the existing localhost-only port-forward and short-lived token
procedure documented in `cloudnativepong/README.md` and `DEPLOYMENT.md`.
