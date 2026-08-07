# Old production Cloud Native Pong game-day drills

These drills are designed for the existing old production single-host
`k3d-pong` deployment, reconciled from `clusters/vmi3474918/` and publicly
addressed at `169.58.97.73`. They are **operator-run and non-destructive by
default**: inspect first, use one bounded failure injection at a time, wait for
the stated observation, and restore the old production GitOps state
immediately.

**Native staging is not a drill target.** Native staging means
`clusters/belacca-production/` on three native servers, including
`169.58.143.41` and `169.58.143.42`; it currently contains the foundation plus
manually staged Traefik only. Native cutover is not started, and no native
Pong/application workload is deployed. Do not run these old production drills
against native staging.

Do not delete old production `k3d-pong`, its namespace, `pong-api-data`, its PV,
or `kube-system/traefik-acme`.

## Common old production preflight

Run from a protected old production operator shell. Redact Secret values and
player data from captured output.

```bash
kubectl config use-context k3d-pong
test "$(kubectl config current-context)" = k3d-pong
kubectl get nodes
kubectl -n pong get deploy,pods,svc,pvc
kubectl -n flux-system get gitrepositories,kustomizations
flux get kustomizations -A
```

Record the current old production Git revisions, deployment image digests,
replica counts, ready conditions, and a baseline check of
`https://pong.belacca.com/health` and `/api/rooms`. The supported old production
public host and redirect inventory is in [`SITES.md`](SITES.md). The scheduled
Pong synthetic targets `https://pong.belacca.com` by default and fails closed if
it cannot execute; a local curl is not an SLO measurement.

Common old production post-drill verification:

```bash
kubectl config use-context k3d-pong
kubectl -n pong rollout status deployment/pong-gateway --timeout=180s
kubectl -n pong rollout status deployment/pong-static --timeout=180s
kubectl -n pong rollout status deployment/pong-api --timeout=180s
kubectl -n pong get pods,svc,pvc
flux get kustomization pong -n flux-system
curl -fsS https://pong.belacca.com/health
curl -fsS https://pong.belacca.com/api/rooms
```

## Old production gateway failure

**Signal:** old production `/health` or the homepage fails while the API/static
pods are Ready; Traefik may show no healthy gateway endpoints.

**Observe:**

```bash
kubectl config use-context k3d-pong
kubectl -n pong get deploy,pods,svc,endpoints pong-gateway
kubectl -n pong describe deploy/pong-gateway
kubectl -n pong logs deploy/pong-gateway --since=10m
kubectl -n kube-system logs deploy/traefik --since=10m | tail -100
```

**Bounded drill:** cordon is not required. Delete one gateway Pod only when two
or more Ready replicas are present and the old production PDB allows it:

```bash
kubectl -n pong get pods -l app=cloudnativepong,component=gateway
kubectl -n pong delete pod <one-pong-gateway-pod> --wait=false
```

If the selector would affect more than one Pod, stop and select one Pod name
explicitly. Verify the replacement becomes Ready and that a WebSocket room
created before the drill is not unexpectedly terminated. Do not scale the
single-writer API during this drill.

**Rollback:** no Git rollback is needed for a Pod-level restart. If an old
production gateway image/configuration rollout caused the fault, revert the
application image/tag commit in `cloudnativepong`, then:

```bash
flux reconcile source git cloudnativepong -n flux-system
flux reconcile kustomization pong -n flux-system --with-source
```

## Old production static service failure

**Signal:** old production gateway `/health` and `/api/rooms` work, but `/` or
static assets return an error or stale/broken content.

**Observe:**

```bash
kubectl config use-context k3d-pong
kubectl -n pong get deploy,pods,svc,endpoints pong-static
kubectl -n pong logs deploy/pong-static --since=10m
kubectl -n pong describe deploy/pong-static
curl -i https://pong.belacca.com/
```

**Bounded drill:** with at least two Ready old production static replicas,
restart one Pod using an explicit name and verify the other replica continues
to serve:

```bash
kubectl -n pong get pods -l app=cloudnativepong,component=static -o name
kubectl -n pong delete pod <one-pong-static-pod> --wait=false
```

Do not delete the Deployment or Service. Do not treat an HTTP 200 fallback page
as proof that JavaScript/API functionality works; run the browser smoke check.

**Rollback:** revert the static image/tag commit and reconcile the old
production child:

```bash
flux reconcile source git cloudnativepong -n flux-system
flux reconcile kustomization pong -n flux-system --with-source
```

## Old production lobby/API failure

**Signal:** old production `/api/rooms` fails, room creation/join fails, or API
readiness is false. The old production SQLite PVC is a dependency and must be
preserved.

**Observe:**

```bash
kubectl config use-context k3d-pong
kubectl -n pong get pod,deploy,svc,pvc pong-api pong-api-data
kubectl -n pong describe pod -l app=cloudnativepong,component=api
kubectl -n pong logs deploy/pong-api --since=10m
kubectl -n pong get events --sort-by=.lastTimestamp | tail -50
```

**Bounded drill:** do not simulate data loss. If testing restart recovery, use
an explicit API Pod deletion while the Deployment remains managed, after
confirming a known-good backup artifact exists:

```bash
kubectl -n pong get pvc pong-api-data
kubectl -n pong get pods -l app=cloudnativepong,component=api -o name
kubectl -n pong delete pod <one-pong-api-pod> --wait=false
kubectl -n pong rollout status deployment/pong-api --timeout=180s
```

Verify old production `/api/rooms` and a two-player journey. Never scale this
Deployment above one and never mount the RWO claim in a second live API Pod.

**Rollback/recovery:** for a bad old production image, revert the application
image/tag commit and reconcile. For suspected SQLite corruption, stop at
diagnosis, preserve the old production PVC, and use the copied artifact with
the isolated rehearsal. Do not copy a backup into the live `/data/pong.db`
path.

## Old production dynamic room failure

**Signal:** an old production room cannot start, one player cannot join, the
room WebSocket closes, or completed room Pods/Services remain.

**Observe:**

```bash
kubectl config use-context k3d-pong
kubectl -n pong get pods,svc -l role=room -o wide
kubectl -n pong get events --sort-by=.lastTimestamp | tail -80
kubectl -n pong logs deploy/pong-api --since=10m
kubectl -n pong describe pod <pong-room-pod>
```

**Bounded drill:** create a test room through the normal old production UI/API,
then observe the generated Pod and Service. Do not manually mutate the room Pod
template or call internal callbacks from outside the namespace. For cleanup
behavior, end the test room normally and wait for the lobby reconciliation
interval.

A stuck terminal room may be inspected and, only after confirming it is not an
active game, removed through the application's normal cleanup path or the
explicit Pod/Service names. Never use a broad `delete pods -l role=room` during
an old production live incident.

**Rollback:** revert the room/API image commit and reconcile the old production
child. Existing active rooms may be lost by an application rollback; notify
players and verify that orphan cleanup does not touch the protected old
production PVC.

## Old production Flux reconciliation failure

**Signal:** an old production source or Kustomization is not Ready, a deployment
differs from Git, or a notification reports reconciliation errors.

**Observe:**

```bash
kubectl config use-context k3d-pong
flux get sources git -A
flux get kustomizations -A
kubectl -n flux-system describe kustomization pong
kubectl -n flux-system get events --sort-by=.lastTimestamp | tail -80
kubectl -n flux-system logs deploy/source-controller --since=10m
kubectl -n flux-system logs deploy/kustomize-controller --since=10m
```

**Bounded drill:** do not alter the old production root `prune` setting and do
not test by removing resources. Use a reviewed, no-op reconciliation:

```bash
flux reconcile source git cloudnativepong -n flux-system
flux reconcile kustomization pong -n flux-system --with-source
```

If an old production platform notification Secret is absent, record it as the
documented external prerequisite; do not create a fake endpoint or value.
Verify the Kustomization's source revision and inventory before any ownership
change.

**Rollback:** revert the offending Git commit in the owning repository, push it,
and reconcile the old production source and Kustomization again. If the
controller itself is unhealthy, follow controller recovery without deleting old
production application PVCs or turning on root pruning.

## Old production NetworkPolicy failure

**Signal:** a previously healthy old production path times out after policy
reconciliation; for example Traefik cannot reach the gateway, gateway cannot
reach static/API, or room callbacks fail.

**Observe:**

```bash
kubectl config use-context k3d-pong
kubectl get networkpolicies -A
kubectl -n pong describe networkpolicy pong-gateway-traffic pong-static-traffic pong-api-traffic
kubectl -n pong get pods -o wide
kubectl -n kube-system get pods -l k8s-app=kube-dns
```

Use an approved, short-lived diagnostic Pod only if its image and access are
already authorized. Test one expected path at a time; a failed connection is
not proof of policy enforcement when the old production CNI does not implement
NetworkPolicy. The checked-in old production policies intentionally leave
dynamic-room/API egress broad until that application contract is tested.

**Bounded drill:** reconcile the existing old production policy set and verify
the documented allow paths. Do not add a blanket allow-all policy as a “test”,
and do not change policies directly in the live old production cluster as a
permanent fix.

```bash
flux reconcile kustomization flux-system -n flux-system --with-source
kubectl -n pong get networkpolicy -o yaml
```

**Rollback:** revert the old production GitOps policy commit and reconcile the
old production root:

```bash
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
```

Never delete all old production NetworkPolicies as recovery; that hides the
failure and changes the security boundary.

## Old production rollback command index

| Failure | Owner | Reversible action |
|---|---|---|
| Gateway/static/lobby/room image or config | `cloudnativepong` | Revert the image/tag commit, reconcile `cloudnativepong`, reconcile old production `pong` |
| Host routing / Traefik config / policy | `belacca-gitops` | Revert the GitOps commit, reconcile old production `flux-system` |
| Flux source/Kustomization state | Flux operator | Fix/revert the source commit; reconcile old production source then Kustomization |
| SQLite restore rehearsal | Local operator | `k3d cluster delete pong-restore-<exact-name>` only; never old production or native staging |

The rehearsal cleanup command is intentionally exact:

```bash
k3d cluster delete pong-restore-<exact-name>
```

Do not substitute `pong`, `k3d-pong`, a wildcard, or a context selected by
current kubeconfig. The isolated runner itself refuses those names. This
isolated deletion is the only deletion described by the rehearsal procedure;
it is not an old production or native staging operation.
