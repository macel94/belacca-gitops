# Multi-project cutover runbook

This runbook documents the completed move from
`macel94/cloudnativepong` to `macel94/belacca-gitops` and the safe procedure for
future resource ownership changes. Flux resources must not be moved between
Kustomizations by replacing the source behind one existing root in a single
commit: the old root inventory can garbage-collect resources before the new
child Kustomization adopts them.

The initial cutover exposed that failure mode. Pong was recovered by its child
Kustomization, the local-path PVC was recreated, and the current database was
backed up outside Git. The recovered PVC is now protected with a `Retain`
reclaim policy and the Pong Namespace/PVC manifests carry Flux prune-disabled
annotations.

## Preconditions

1. DNS A records exist and have propagated:
   - `pong.belacca.com` → `169.58.97.73`
   - `francesco.belacca.com` → `169.58.97.73`
2. The portfolio image has been published to GHCR and the package is public,
   or the cluster has a pull secret configured.
3. DNS A records resolve publicly. Traefik uses TLS-ALPN-01, so public 443 must
   reach the cluster for certificate issuance. HTTP redirects are router-level
   rules and must produce standard `https://host/` URLs.
4. `npm test`, Pong Go tests, Kustomize render, and CI checks pass.
5. Keep the current cluster context as `k3d-pong` and do not delete/recreate it.

## Stage 1 — publish the portfolio repository only

Do **not** push the Pong Ingress deletion yet: the current Flux root still
watches `cloudnativepong` and would prune the live route before the new platform
root is active.

```bash
cd /root/sources/francesco-belacca-site
npm test
git add .
git commit -m "feat: launch Francesco Belacca personal site"
git push origin main
```

Wait for the workflow to publish `ghcr.io/macel94/francesco-belacca-site:sha-*`
and its generated deployment-tag commit. Set that package to **Public** in
GitHub Packages, then confirm:

```bash
gh run list -R macel94/francesco-belacca-site --limit 5
kubectl kustomize deploy | grep 'ghcr.io/macel94/francesco-belacca-site'
```

Push `belacca-gitops` next, still with `prune: false` in its Flux bootstrap.
Keep the legacy Pong Ingress files in the Pong repository for this stage so the
current Flux root remains safe until Stage 2.

## Stage 2 — prepare ownership transfer before changing sources

For a future move from one Flux Kustomization to another, first commit and
reconcile `prune: false` in the **old** Kustomization while it still watches
its old repository. Verify the live object:

```bash
flux export kustomization flux-system -n flux-system | grep -A2 prune
```

For stateful resources, also add
`kustomize.toolkit.fluxcd.io/prune: disabled` to the Namespace and PVC, and set
the underlying PV reclaim policy to `Retain`. Only after the old inventory has
stopped pruning may the new Kustomization apply the same resources.

The initial cutover did not follow this order; changing the root source and
inventory together caused the old root to delete Pong before adoption. Do not
repeat that operation. The current cluster is already on the new root, so the
remaining stages below are the applicable verification/cleanup steps.

## Stage 3 — move Pong routing ownership

The new `pong`, `portfolio`, and `belacca-routing` Kustomizations are now
Ready. Push the Pong change that removes `k8s/overlays/server/ingress.yaml`
and `ingress-tls.yaml`. The child Pong Kustomization owns the workload tree and
will prune those old Ingresses; the platform routing Kustomization owns the new
host-specific routes. The Namespace and PVC prune annotations protect the
stateful data during this cleanup.

```bash
cd /root/sources/cloudnativepong
go test ./...
git add README.md DEPLOYMENT.md HANDOFF.md clusters k8s/base/all.yaml k8s/overlays/server/kustomization.yaml k8s/overlays/server/ingress.yaml k8s/overlays/server/ingress-tls.yaml
git commit -m "feat: move Pong to pong subdomain"
git push origin main
```

After reconciliation, verify:

```bash
kubectl -n pong get namespace,pvc,pv
kubectl -n pong get ingress
kubectl -n flux-system get kustomization pong belacca-routing
```

## Stage 4 — verify public behavior

```bash
curl -fsS https://francesco.belacca.com/ | grep -q 'Systems, under load.'
curl -I https://belacca.com/
curl -I https://www.belacca.com/
curl -fsS https://pong.belacca.com/ | grep -q '<!DOCTYPE'
curl -fsS https://pong.belacca.com/api/rooms
```

Use a browser to open Pong, create a room, join it from a second browser, and
confirm WebSocket play. Check that no old wildcard Ingress remains:

```bash
kubectl -n pong get ingress
kubectl -n portfolio get ingress
kubectl -n flux-system get kustomizations
```

## Stage 5 — enable platform-root pruning only after verification

The platform root currently remains at `prune: false` as a deliberate guard
while the cutover is validated. After DNS, TLS, host routing, Pong WebSockets,
and the resource inventory are verified, change
`clusters/vmi3474918/flux-system/gotk-sync.yaml` from `prune: false` to
`prune: true`, commit, push, and reconcile. This root owns platform resources
and child Flux objects; the Pong child owns Pong workloads. Never remove the
Pong prune annotations or delete the database PVC as part of this step.

## Rollback

If the platform source fails before the new child resources are Ready, restore
the old repository URL in `GitRepository/flux-system` and reconcile:

```bash
kubectl -n flux-system patch gitrepository flux-system --type merge \
  -p '{"spec":{"url":"https://github.com/macel94/cloudnativepong.git"}}'
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
```

Because the current bootstrap root uses `prune: false`, rollback is a
repository/source operation, not a destructive cluster operation. If routing
is already switched, revert the platform routing commit and reconcile the
platform source. Do not switch the root back to the old repository unless the
old Kustomization has first been reconciled with `prune: false` and its
stateful resources are protected. Never delete `pong-api-data`, its PV,
`kube-system/traefik-acme`, or the entire cluster as a rollback.
