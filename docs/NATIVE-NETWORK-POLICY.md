# Native production NetworkPolicy verification

This is the native production boundary for issue #9. It is deliberately split
between checked-in policy intent and live evidence. Kubernetes documents that a
`NetworkPolicy` object has no effect unless the cluster network plugin enforces
it; rendered YAML is therefore not proof of runtime isolation.

## Dependency graph

The native Pong source is the pinned `cloudnativepong` native-staging overlay.
The room contract is stable even though room Pods and Services are dynamic:

```text
host-network Traefik :80/:443
  -> pong-gateway :8080
       -> pong-static :8080
       -> pong-api :8080
            -> Kubernetes API Service :443 (create/list/watch/delete room Pods/Services)
            -> pong-room-<id> Service/Pod :8080
pong-room-<id> :8080
  -> pong-api :8080 (/internal/rooms/<id>/{started,finished})
Prometheus -> pong-api /metrics
Prometheus -> Flux controller metrics :8080
analytics/headlamp OAuth2 Proxy -> Dex issuer (HTTPS) and in-namespace upstream
Longhorn chart-owned policies -> Longhorn manager/engine/webhook graph
```

Dynamic resources are selected by the labels the application itself creates:
`app=cloudnativepong,role=room` for room Pods and the same labels plus
`room-id` for room Services. No policy depends on an individual room ID.

The checked-in contract is `clusters/belacca-production/policies/edge-contract.json`.
The policy child is `native-policies`, and it waits for the Pong, observability,
and Dex children. Longhorn's chart-owned `k3s` policy set is enabled in
`clusters/belacca-production/longhorn/helmrelease.yaml`; its current templates
are ingress policies for manager/instance-manager/webhook paths. This
repository does not duplicate a partial Longhorn policy that could break
replica traffic; the live probe must verify the chart-generated policies and
replica path before calling storage isolation complete.

## Enforcement gate (must happen before relying on the policy)

The following is an operator action, not CI pretending to have production
access. Production credentials, the native kubeconfig, CNI identity, and an
approved diagnostic image are not in this repository. The probe fails closed
when any of them is absent.

1. Use the intended context and inspect, without applying anything:

   ```bash
   kubectl config use-context belacca-native
   kubectl get nodes -o wide
   kubectl get pods -A -o wide
   kubectl get networkpolicy -A
   kubectl -n kube-system get pods -o wide
   kubectl -n kube-system get ds,deploy -o yaml > /tmp/native-networking-components.yaml
   kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.podCIDR}{"\n"}{end}'
   kubectl get svc kubernetes -o wide
   ```

2. Record the actual CNI/network-policy controller identity and its version in
   the evidence record. For a K3s custom CNI, also record that K3s was started
   with `--flannel-backend=none` and `--disable-network-policy` where the CNI
   supplies its own policy engine. Never call Flannel alone an enforcing CNI.

3. Use an approved image pinned by digest and an authorized identity. Run the
   complete probe only after a real room exists:

   ```bash
   export KUBE_CONTEXT=belacca-native
   export CNI_IDENTITY='<verified-cni-controller-and-version>'
   export DIAGNOSTIC_IMAGE='registry.example/approved-netshoot@sha256:<64-hex-digest>'
   export ROOM_SERVICE='pong-room-<six-hex-id>'
   export EVIDENCE_FILE="$PWD/native-network-policy-$(date -u +%Y%m%dT%H%M%SZ).txt"
   scripts/verify-native-network-policy.sh
   ```

   The script checks the service CIDR/API VIP, creates only short-lived
   diagnostic Pods, tests every required and forbidden edge, and removes all
   diagnostic Pods/namespaces in an exit trap. It emits only edge IDs and pass /
   fail status; do not commit the evidence file because it contains live
   topology metadata.

4. A successful run is valid only when all of these are true:

   - the context is exactly `belacca-native`;
   - CNI identity and version are recorded;
   - `kubernetes.default` is `10.43.0.1`, matching the checked-in `/32` rule;
   - every required edge is `pass`;
   - every forbidden edge is `pass` (meaning unreachable); and
   - cleanup is `pass` and the diagnostic resources are gone.

   A timeout caused by an unhealthy target, missing room, image pull failure,
   DNS failure, or unknown CNI is **inconclusive**, not evidence of denial.

### Host-network edge source behavior

The host-network Traefik edge has two legitimate source forms at protected
backends: same-node traffic retains the Traefik workload identity, while
cross-node flannel-wireguard forwarding is observed by the NetworkPolicy layer
as one of the three node flannel interface addresses (`10.42.0.0/32`,
`10.42.1.0/32`, or `10.42.2.0/32`). The policies admit only those exact
interface addresses alongside the public node `/32` fallback; the entire
`10.42.0.0/16` Pod CIDR is never an allowed source. This narrow exception is
required for active-active host-network routing and prevents cross-node edge
requests from becoming false 502s.

## Required paths

`edge-contract.json` is the machine-readable source of IDs. Its
`required_edges` and `forbidden_edges` arrays are the reviewable test plan. The
live probe covers:

- host-network Traefik to the gateway, with the public `/health` check on a
  declared native node address;
- gateway to static and API;
- API to a real dynamically-created room Service and to the Kubernetes API;
- room callback to the API health endpoint (the application callback paths are
  `/internal/rooms/<id>/started` and `/finished`);
- Pong DNS to kube-dns over UDP/TCP 53;
- Prometheus to Pong and Flux controller metrics;
- analytics and Headlamp OAuth2 Proxy to the Dex issuer, analytics proxy to
  GoatCounter, and Headlamp proxy to Headlamp; and
- Longhorn manager label/port reachability and the chart-generated manager
  policy; replica/engine paths remain a live chart/CNI verification gate.

The probe is the runtime test. The checked-in validator is only a deterministic
review guard and never claims these paths were live-tested.

## Forbidden paths

The clean, unlabeled diagnostic namespace must not reach:

- Pong API or a dynamic room;
- Dex on TCP/5556;
- Flux kustomize-controller metrics on TCP/8080; or
- Longhorn manager on TCP/9500.

The source diagnostic Pod is authorized and short-lived, but has no workload
labels or ServiceAccount token. If any forbidden connection succeeds, stop,
record the edge ID, and roll back the policy change. Do not add an allow-all
policy to investigate.

## Native limitations and explicit follow-up

No production cluster, credentials, CNI inspection, authorized diagnostic
identity, or real room is available in this worktree. Consequently this branch
contains no fabricated CNI result or runtime evidence. The coordinating
operator must run the probe after reconciliation and attach the redacted output
as release evidence.

External Google connectivity and exact Longhorn engine/replica behavior are
runtime properties. The checked-in policies do not invent Google CIDRs or a
partial Longhorn graph. Dex/Google and the complete Longhorn chart policy must
be included in the same live evidence run; failure is a release block until the
operator records the chart/CNI result and updates the contract if the reviewed
runtime differs.

## Rollback

Policy owner is `belacca-gitops`. Roll back the Git commit that introduced the
policy, then reconcile only the native root after verifying the revision:

```bash
git revert <policy-commit>
git push origin <reviewed-rollback-branch>
kubectl config use-context belacca-native
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
flux reconcile kustomization native-policies -n flux-system --with-source
```

The operator must use the actual reviewed branch/commit and normal protected
Git workflow; never apply a blanket allow policy or delete all NetworkPolicies.
If policy reconciliation is stuck, restore the last known-good policy commit
through Git and reconcile. Keep Pong PVCs, Longhorn volumes, and namespaces.

## Game day

Run this bounded drill after policy rollout and at least during a quarterly
security game day:

1. Reconcile `native-policies` and capture its revision, status, and inventory.
2. Run the probe with one normal two-player room. Verify required/forbidden edge
   evidence and diagnostic cleanup.
3. Run the normal Pong synthetic journey: homepage, health, room create, join,
   two-player WebSocket playing state, and room cleanup. Confirm no room Pod or
   Service remains afterward.
4. Inspect DNS, Flux, Prometheus, Dex, analytics, and Longhorn health. A failed
   control-plane or external identity path is a failed drill, not a policy pass.
5. Exercise rollback in the approved change process and repeat the normal
   Pong journey. Record timestamps, policy revision, CNI identity, failed edge
   ID, and the exact recovery commit.

Do not use native production as a test target. Do not store
room IDs, player names, tokens, response bodies, or credentials in evidence.
