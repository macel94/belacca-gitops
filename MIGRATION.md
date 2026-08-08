# Old production to native staging migration runbook

## Status and vocabulary

The historical application ownership move into **old production** is complete.
Old production is the existing `k3d-pong` cluster, reconciled from
`clusters/vmi3474918/`, with public address `169.58.97.73`.

**Native staging** is the separate `clusters/belacca-production/` tree for
three native servers, including `169.58.143.41` and `169.58.143.42`.
It currently contains the cluster foundation, published route-less Pong and
portfolio Kustomizations, and Flux-managed Traefik. The native root and both
application Kustomizations reconcile successfully: private ClusterIP Pong and
portfolio staging workloads are live. Public application routes, native SSO,
analytics, and native observability are not deployed.

**Native cutover: not started.** Native staging is not a replacement root for
old production. Do not redirect old production DNS, move old production Flux
inventories, or use old production rollback commands against native staging.

This runbook therefore has two clearly separated parts: the completed old
production ownership history and the safety boundary for a future native
cutover. Flux resources must not be moved between Kustomizations by replacing
the source behind one existing root in a single commit: the old root inventory
can garbage-collect resources before the new child Kustomization adopts them.

The initial old production cutover exposed that failure mode. Pong was
recovered by its child Kustomization, the local-path PVC was recreated, and the
current database was backed up outside Git. The recovered PVC is now protected
with a `Retain` reclaim policy and the Pong Namespace/PVC manifests carry Flux
prune-disabled annotations.

## Old production preconditions

These preconditions apply only to the existing old production migration and
verification work:

1. DNS A records exist and have propagated:
   - `pong.belacca.com` → `169.58.97.73`
   - `francesco.belacca.com` → `169.58.97.73`
   - `belacca.com`, `www.belacca.com`, and `www.francesco.belacca.com` → `169.58.97.73`
2. The portfolio image has been published to GHCR and the package is public,
   or old production has a pull secret configured.
3. DNS A records resolve publicly. The committed old production Traefik
   configuration uses Cloudflare DNS-01, with the token supplied by the
   out-of-band `kube-system/traefik-cloudflare` Secret under the
   `CLOUDFLARE_DNS_API_TOKEN` key. Public port 443 must reach old production
   Traefik for normal HTTPS traffic; port 80 is useful for the explicit
   redirect but is not the ACME challenge path. HTTP redirects are router-level
   rules and must produce standard `https://host/` URLs.
4. `npm test`, Pong Go tests, old production Kustomize render, and CI checks
   pass.
5. Keep the current old production cluster context as `k3d-pong` and do not
   delete or recreate it.

Native staging has separate infrastructure prerequisites and must not be
substituted for any of these old production checks. Its native `.41`/`.42` hosts are
not the old production public DNS target.

## Old production Stage 1 — publish the portfolio repository only

Do **not** push the Pong Ingress deletion yet: the current old production Flux
root still watches `cloudnativepong` and would prune the live route before the
new platform root is active.

```bash
cd /root/sources/francesco-belacca-site
npm test
git add .
git commit -m "feat: launch Francesco Belacca personal site"
git push origin main
```

Wait for the workflow to publish
`ghcr.io/macel94/francesco-belacca-site:sha-*` and its generated
deployment-tag commit. Set that package to **Public** in GitHub Packages, then
confirm:

```bash
gh run list -R macel94/francesco-belacca-site --limit 5
kubectl kustomize deploy | grep 'ghcr.io/macel94/francesco-belacca-site'
```

Push `belacca-gitops` next, still with `prune: false` in its old production Flux
bootstrap. Keep the legacy Pong Ingress files in the Pong repository for this
stage so the current old production Flux root remains safe until Stage 2.

## Old production Stage 2 — prepare ownership transfer before changing sources

For a future move from one old production Flux Kustomization to another, first
commit and reconcile `prune: false` in the **old** Kustomization while it still
watches its old repository. Verify the live object:

```bash
flux export kustomization flux-system -n flux-system | grep -A2 prune
```

For stateful resources, also add
`kustomize.toolkit.fluxcd.io/prune: disabled` to the Namespace and PVC, and set
the underlying PV reclaim policy to `Retain`. Only after the old inventory has
stopped pruning may the new Kustomization apply the same resources.

The initial old production cutover did not follow this order; changing the root
source and inventory together caused the old root to delete Pong before
adoption. Do not repeat that operation. The current old production cluster is
already on the new root, so the remaining stages below are the applicable
verification/cleanup steps.

## Old production Stage 3 — move Pong routing ownership

The old production `pong`, `portfolio`, and `belacca-routing` Kustomizations are
now Ready. Push the Pong change that removes `k8s/overlays/server/ingress.yaml`
and `ingress-tls.yaml`. The old production child Pong Kustomization owns the
workload tree and will prune those old Ingresses; the old production routing
Kustomization owns the new host-specific routes. The Namespace and PVC prune
annotations protect the stateful data during this cleanup.

```bash
cd /root/sources/cloudnativepong
go test ./...
git add README.md DEPLOYMENT.md clusters k8s/base/all.yaml k8s/overlays/server/kustomization.yaml k8s/overlays/server/ingress.yaml k8s/overlays/server/ingress-tls.yaml
git commit -m "feat: move Pong to pong subdomain"
git push origin main
```

After old production reconciliation, verify:

```bash
kubectl config use-context k3d-pong
kubectl -n pong get namespace,pvc,pv
kubectl -n pong get ingress
kubectl -n flux-system get kustomization pong belacca-routing
```

## Old production Stage 4 — verify public behavior

```bash
curl -fsS https://francesco.belacca.com/ | grep -q 'Systems, under load.'
curl -I https://belacca.com/
curl -I https://www.belacca.com/
curl -I https://www.francesco.belacca.com/
curl -fsS https://pong.belacca.com/ | grep -q '<!DOCTYPE'
curl -fsS https://pong.belacca.com/api/rooms
```

Use a browser to open old production Pong, create a room, join it from a second
browser, and confirm WebSocket play. Check that no old wildcard Ingress remains:

```bash
kubectl -n pong get ingress
kubectl -n portfolio get ingress
kubectl -n flux-system get kustomizations
```

## Old production Stage 5 — enable platform-root pruning

The old production ownership migration passed its safety gates and the old
production platform root is set to `prune: true` in
`clusters/vmi3474918/flux-system/gotk-sync.yaml`. Before making that change, we
verified that:

- every object in the live old production root inventory is present in the
  checked-in old production root render;
- the `pong`, `portfolio`, `analytics`, and `belacca-routing` child inventories
  are disjoint and each child is Ready;
- the old production root owns platform infrastructure and child Flux objects,
  while child Kustomizations own application and routing resources;
- the Pong and analytics Namespaces/PVCs are annotated with
  `kustomize.toolkit.fluxcd.io/prune: disabled`;
- the old production ACME PVC is also explicitly prune-protected; and
- the old production Pong PV reclaim policy is `Retain`.

The old production staged `observability` child remains deliberately at
`prune: false` until its resource budget, CNI behavior, and target health are
separately validated. Old production root pruning does not change that child
setting. Publish the old production GitOps change, wait for the root to
reconcile, and repeat the inventory and protected-state checks before treating
the old production ownership migration as complete. The old production root
owns platform resources and child Flux objects; the Pong child owns Pong
workloads. Never remove the prune annotations or delete a database/ACME PVC as
part of this step.

## Native staging boundary — cutover not started

The native staging tree at `clusters/belacca-production/` contains its
foundation, published Pong and portfolio Kustomizations, Flux-managed Traefik,
and native cert-manager DNS-01/TLS and routing resources. It is a staging
target for three native servers, not a cutover target. The root and both
application Kustomizations are Ready. In particular:

- native routes target only the deployed portfolio and Pong Services, with
  explicit cert-manager TLS Secrets and no old-production state ownership;
- the Cloudflare DNS-01 credential is SOPS/age-encrypted in Git, while its
  plaintext remains out of band; no public DNS record is changed by this tree;
- no native analytics, dashboard, Dex, Flux Web UI, or observability workload
  is currently deployed, so their hostnames have no native Certificates or
  routes;
- no old production application inventory has been adopted by native staging;
- no old production DNS record points to the native `.41`/`.42` hosts; and
- no native cutover date, ownership transfer, or rollback target has started.

A future native cutover requires a separate reviewed sequence: establish the
native cluster and storage/network prerequisites, render and validate each
application tree, stage ownership with pruning disabled, validate the
out-of-band Cloudflare DNS-01 credential and native certificate handling,
verify protected state and route behavior, and only then plan DNS and workload
migration. The native TLS/routing directories remain limited to the deployed
portfolio and Pong targets; adding other services or changing public DNS is a
separate gate. Removing the cert-manager child from the native root is the
rollback boundary for the controller staging step; its CRDs are configured to
be kept. Until that work is explicitly completed, old production remains the
only application production environment.

## Old production rollback

If the old production platform source fails after old production root pruning is
enabled, revert the GitOps commit and reconcile the old production root from the
reviewed revision:

```bash
kubectl config use-context k3d-pong
kubectl -n flux-system patch gitrepository flux-system --type merge \
  -p '{"spec":{"url":"https://github.com/macel94/cloudnativepong.git"}}'
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
```

An old production rollback must be a reviewed Git revert, not an ad-hoc source
swap. If the old production root source itself must be changed, first suspend or
set the active old production root to `prune: false`, reconcile that change, and
verify the old/new inventories and stateful-resource protections before
switching sources. If old production routing is already switched, revert the
old production platform routing commit and reconcile the old production source.
Never delete `pong-api-data`, its PV, `analytics/goatcounter-data`,
`kube-system/traefik-acme`, or the entire old production cluster as a rollback.
Do not use this rollback block as a native staging cutover procedure.
