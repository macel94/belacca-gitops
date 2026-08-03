# Multi-project cutover runbook

This runbook moves the existing Flux root from
`macel94/cloudnativepong` to `macel94/belacca-gitops` without deleting the
Pong SQLite PVC or causing an avoidable routing outage.

## Preconditions

1. DNS A records exist and have propagated:
   - `pong.belacca.com` → `169.58.97.73`
   - `francesco.belacca.com` → `169.58.97.73`
2. The portfolio image has been published to GHCR and the package is public,
   or the cluster has a pull secret configured.
3. `npm test`, Pong Go tests, Kustomize render, and CI checks pass.
4. Keep the current cluster context as `k3d-pong` and do not delete/recreate it.

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

## Stage 2 — switch Flux source, preserving inventory

The existing Flux `GitRepository/flux-system` points at the old application
repository. Patch only its repository URL in-place; retain the existing Secret
and never print or recreate its credentials:

```bash
kubectl -n flux-system patch gitrepository flux-system --type merge \
  -p '{"spec":{"url":"https://github.com/macel94/belacca-gitops.git"}}'
```

The existing `flux-system` Secret remains the credential source for the new
public repository. Reconcile the source and root, then inspect conditions:

```bash
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
flux get sources git -A
flux get kustomizations -A
```

The platform root starts with `prune: false`, so old inventory is not deleted
while the child sources are adopted. Wait for `pong`, `portfolio`, and then
`belacca-routing` to be Ready. Confirm the new portfolio has two Ready pods and
that the existing `pong-api-data` PVC remains Bound. The new `pong-host`
Ingress and portfolio Ingress have higher priority than the old wildcard route.

## Stage 3 — move Pong routing ownership

After the new `pong`, `portfolio`, and `belacca-routing` Kustomizations are
Ready, push the Pong change that removes `k8s/overlays/server/ingress.yaml` and
`ingress-tls.yaml`. The child Pong Kustomization now owns the workload tree and
will prune those old Ingresses; the platform routing Kustomization owns the new
host-specific routes. Confirm the `pong-api-data` PVC remains Bound.

```bash
cd /root/sources/cloudnativepong
go test ./...
git add README.md DEPLOYMENT.md HANDOFF.md clusters k8s/overlays/server/kustomization.yaml k8s/overlays/server/ingress.yaml k8s/overlays/server/ingress-tls.yaml
git commit -m "feat: move Pong to pong subdomain"
git push origin main
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

## Stage 5 — enable pruning after the handoff

Only after all resources are confirmed healthy, change
`clusters/vmi3474918/flux-system/gotk-sync.yaml` from `prune: false` to
`prune: true`, commit, push, and reconcile. The new platform root then owns the
cluster tree and can prune resources removed from its source. Do not delete the
old Flux Kustomization separately; the new root has the same name and replaces
it through reconciliation.

## Rollback

If the platform source fails before the new child resources are Ready, restore
the old repository URL in `GitRepository/flux-system` and reconcile:

```bash
kubectl -n flux-system patch gitrepository flux-system --type merge \
  -p '{"spec":{"url":"https://github.com/macel94/cloudnativepong.git"}}'
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
```

Because the bootstrap root uses `prune: false`, this rollback does not remove
existing workloads. If routing was already switched, revert the platform
routing commit and reconcile after the old source is restored. Never delete
`pong-api-data`, `kube-system/traefik-acme`, or the entire cluster as a rollback.
