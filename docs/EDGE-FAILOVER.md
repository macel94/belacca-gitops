# Native API and public-ingress failover

## Status and safety boundary

This document is the operator runbook for issue #7. The machine-readable design
is [`../clusters/belacca-production/edge/failover-contract.json`](../clusters/belacca-production/edge/failover-contract.json),
and the evidence record is
[`evidence/api-edge-failover.json`](evidence/api-edge-failover.json).

**Current status: selected design, not provisioned or proven.** Contabo is the
selected provider for a provider-managed L4 load balancer/VIP, but this
repository has no provider credentials, provider VIP, live firewall access, or
native cluster context. No production action or failover result is claimed.
The evidence file intentionally contains no VIP, operator, timestamp, or
measurement. Do not change its status to `complete` without an authorized live
drill and redacted raw evidence.

Until the gates below pass, DNS remains the passive fallback: application hosts
use direct DNS-only records for `.73`, `.41`, and `.42`, and
`k3s-api.belacca.com` uses `.41` and `.42`. This is not health-aware. Use the
manual DNS-removal procedure in this document when an endpoint is unhealthy.
Do not publish a provider VIP alongside the old backend A records.

## Target architecture

```text
                        DNS-only A
  public hosts ────────> one provider VIP ──────┬── TCP 80  ──> node:80  Traefik
  k3s-api.belacca.com ─> one provider VIP ──────┼── TCP 443 ─> node:443 Traefik
                                                └── TCP 6443 -> node:6443 k3s API

  provider LB health/data plane -> only 80/443/6443 on the three control-plane nodes
  Internet/provider LB          -X-> etcd, kubelet, overlay, Longhorn, metrics, SSH
```

The provider VIP is the sole public frontend owner. It is an L4 TCP/TLS
pass-through load balancer; it does not terminate application or Kubernetes API
TLS. Native Traefik continues to terminate public HTTPS, and each k3s API server
continues to present the Kubernetes API certificate. The pool is active-active,
not active/passive: all three control-plane nodes may receive traffic while
healthy. “Passive fallback” refers only to the current manual DNS procedure,
not to a second VIP owner.

The contract allows only these public/backend listeners:

| Purpose | Port | Health signal |
| --- | ---: | --- |
| Existing HTTP redirect | 80/TCP | Gated by the 443 edge check; no new application listener |
| Public ingress | 443/TCP | Validated HTTPS `GET /health` with host/SNI `francesco.belacca.com`, HTTP 200 |
| Kubernetes API | 6443/TCP | Validated HTTPS `GET /readyz` with host/SNI `k3s-api.belacca.com`, HTTP 200 |

The provider must not forward or probe 2379/2380 (etcd), 8472 (k3s Flannel),
9500–9503 (Longhorn data plane), 10250 (kubelet), 9090 (private Prometheus),
SSH, or arbitrary NodePort ranges. The node firewall must enforce this even if
the provider configuration is accidentally broadened.

## Health and convergence policy

Configure both pools with the following policy, represented in the contract:

- probe every 5 seconds with a 2-second timeout;
- withdraw after 3 consecutive failures (at most approximately 15 seconds,
  plus provider scheduling/connection time);
- re-add after 2 consecutive successes (at least approximately 10 seconds);
- use HTTP status 200, not a body substring, as the success criterion;
- preserve existing TCP connections according to the provider's documented
  drain behavior, but send no new connections to a withdrawn backend; and
- record provider timestamps for the first failed check, withdrawal, first
  successful recovery check, re-add, and client convergence.

The Kubernetes API health check must validate the cluster CA or an approved
pinned server certificate and use SNI/Host `k3s-api.belacca.com`. Never use
`--insecure`, accept any certificate, or treat an open 6443 socket as API
readiness. Kubernetes documents `/readyz` as the readiness endpoint and says
health checkers should rely on HTTP status 200. The public edge check must
validate the public CA chain and hostname.

A live drill is complete only when the redacted evidence records all of these
for both an edge failure and a control-plane failure:

1. UTC start and stop timestamps for the injected failure;
2. time to provider withdrawal;
3. time to provider re-add after recovery;
4. client-observed convergence, measured by repeated requests to the stable
   hostname rather than direct backend IPs;
5. API availability through the stable kubeconfig endpoint during the
   control-plane failure; and
6. a port scan or equivalent firewall evidence showing only 80/443/6443 are
   reachable from the provider data plane and no denied port is publicly
   reachable.

Do not write real client tokens, room/player data, private IP telemetry, or
provider credentials into the evidence file. Use identifiers and aggregate
numbers only.

## Provisioning gates (operator-owned)

Complete these in a maintenance window. Stop at any failed gate; there is no
safe Git-only shortcut.

### 1. Confirm provider capability and reserve the VIP

The platform owner must confirm in Contabo's current account/API that the
selected service supports:

- one stable IPv4 VIP with DNS-only A records;
- separate TCP listeners/pools for 80, 443, and 6443;
- TLS-aware HTTPS health checks with configurable SNI/Host and status code;
- independent backend withdrawal/re-add thresholds and connection draining;
- source-address visibility or documented LB data-plane CIDRs for firewalling;
- an audit log of pool changes and health transitions; and
- no implicit exposure of all node ports.

Record the allocated VIP, provider service identifier, health-check policy,
LB source CIDRs, owner, and rollback contact in the approved private
infrastructure record. Do not put credentials or provider API responses in Git.
If Contabo cannot meet these requirements, pause and select a reviewed
provider-managed TCP LB or a separately operated HAProxy/keepalived pair; do
not improvise node-level VIP ownership.

### 2. Prepare API identity and client access

On **each** k3s server, add the stable name to the server TLS SAN configuration
using the reviewed k3s configuration mechanism (`--tls-san
k3s-api.belacca.com`). K3s documents `--tls-san` as adding a hostname/IP to the
server certificate and `--tls-san-security` as restricting unapproved names.
Restart or otherwise roll the servers one at a time, preserving etcd quorum.
Confirm the resulting server certificate contains:

```text
DNS:k3s-api.belacca.com
```

Before changing clients, validate the complete chain through the future VIP
with SNI and the cluster CA. Then update the operator kubeconfig `server` to:

```text
https://k3s-api.belacca.com:6443
```

K3s stores its admin kubeconfig at `/etc/rancher/k3s/k3s.yaml`; copied kubeconfigs
contain inline credentials/certificates and must be rotated or refreshed using
the protected operator process. Never commit a kubeconfig, client key, token,
CA bundle, or provider secret. Validate `kubectl get --raw=/readyz` and a
read-only `kubectl get nodes` through the stable endpoint before cutover.

### 3. Fence node listeners

Apply the reviewed host firewall policy before attaching the VIP:

- allow provider LB source CIDRs to TCP 80, 443, and 6443 only;
- allow the required operator/private administration sources separately;
- deny provider LB and Internet access to 2379, 2380, 8472, 9500–9503,
  10250, 9090, SSH, and all other node ports;
- do not run keepalived, bind the VIP, or add a second public listener on any
  k3s node; and
- verify the denial from an external vantage point and from the provider LB
  data plane where the provider supports that test.

The provider health checks must be permitted to reach only their configured
backend ports. A successful check on 6443 is not permission to reach kubelet or
etcd.

### 4. Configure pools, then test privately

Create the provider pools without changing DNS:

- API pool: all three node IPs, TCP 6443, HTTPS `/readyz`, API hostname/SNI,
  status 200, `fall=3`, `rise=2`;
- edge pool: all three node IPs, TCP 443, HTTPS `/health`, portfolio
  hostname/SNI, status 200, `fall=3`, `rise=2`;
- HTTP listener: TCP 80 to the same edge pool/backends, with no independent
  health signal or unexpected TLS termination; and
- no listener, pool member, or check for any denied port.

Use the provider's private/test address or an authorized direct probe to confirm
TLS pass-through, certificate identity, `/readyz`, `/health`, and the existing
HTTP-to-HTTPS redirect. Do not put the VIP into public DNS until all checks are
successful.

### 5. Cut DNS over without split brain

Lower the old DNS TTL only through the approved Cloudflare change process, then
switch each supported application hostname and `k3s-api.belacca.com` to one
DNS-only A record pointing to the provider VIP. Remove the old backend A records
from the public records in the same reviewed change. Do not publish a CNAME or
proxy mode that changes TLS termination without a separate review.

After TTL expiry, query at least two independent public resolvers and probe the
stable hostnames with normal certificate validation. Keep the old record values
in the private change ticket for rollback; do not restore them while the VIP is
still live unless the provider path has been deliberately withdrawn.

## Failure and recovery drills

Run each scenario only after the provisioning gates pass. Capture timestamps in
UTC and update the evidence JSON only after the drill. An operator must preserve
etcd quorum and must not delete PVCs or mutate application state.

### One-edge failure

1. Baseline the stable portfolio `/health`, Pong `/health`, API `/readyz`, and
   one representative TLS route through the provider VIP.
2. Select exactly one named node and record its current health status. Inject a
   reversible edge-only failure (for example, stop/cordon the node's Traefik
   edge in the approved procedure) without disrupting the other control-plane
   members.
3. Confirm the provider withdraws that node from the 443 pool after three
   failed checks and that new requests through the stable public hostname
   continue through a healthy edge. Check that 80 follows the same healthy
   backend set.
4. Confirm no internal port becomes reachable during the drill.
5. Restore Traefik/node health, wait for two successful checks, and confirm the
   provider re-adds the node. Verify the public certificate and representative
   routes again.
6. Record failure-to-withdraw, recovery-to-readd, and client-convergence
   seconds. If the provider does not expose exact transition timestamps, use
   the smallest defensible interval from probes and mark the measurement method
   in the private ticket.

Do not call an edge drill successful merely because one curl happened to pass;
prove the failed node was withdrawn and later re-added.

### One-control-plane failure

1. Confirm all three control-plane nodes are Ready and etcd has quorum. Record
   the stable API `/readyz` result and a read-only API request.
2. Select exactly one named control-plane node. Use the approved one-node
   failure method; do not stop two servers, delete etcd data, or alter the
   Longhorn/PVC state.
3. Verify the API provider pool withdraws the failed node and that a fresh
   kubeconfig request to `https://k3s-api.belacca.com:6443` succeeds through
   another backend. Verify the public 443 pool also withdraws the same node if
   its edge is unavailable.
4. Confirm the denied ports remain unreachable and no health check targets them.
5. Restore the node using the standard k3s recovery procedure, wait for it to
   rejoin and become Ready, then confirm `/readyz` and the provider re-add.
6. Record API availability during the failure and all convergence timings.

A control-plane node that answers TCP 6443 but returns a non-200 `/readyz` is
unhealthy and must remain withdrawn. Never re-add it based on a socket check.

## Manual DNS-removal fallback (active until proven)

This is the reviewed emergency procedure while direct DNS remains in use and
also the fallback if the provider VIP fails. It is intentionally manual and
requires a second operator to review the exact hostname and address.

1. Confirm the failing address using independent probes pinned to the address,
   with the correct Host/SNI. For the API, use `/readyz` over TLS; for public
   ingress, use `https://francesco.belacca.com/health` and one affected route.
2. Check the node and Flux/Kubernetes status before changing DNS. If only one
   application is unhealthy, prefer fixing/routing the workload rather than
   withdrawing the whole edge. If the node or Traefik is unhealthy, record the
   incident ID and UTC time.
3. In Cloudflare, list the exact DNS-only A record for the hostname. Remove
   **only** the unhealthy address; do not delete the record, change nameservers,
   enable proxying, or remove the remaining healthy addresses.
4. Query two independent public resolvers and repeat pinned and ordinary
   hostname probes. Continue monitoring because resolver caches may retain the
   address until TTL expiry.
5. When the node is repaired, do not immediately restore its A record. First
   run the same direct health checks for 10 minutes, verify the certificate and
   firewall boundary, and obtain a second-operator review. Restore the address
   through the same change process and measure resolver convergence.
6. Record the removed address, hostname, reason, timestamps, resolver results,
   and restoration decision without storing credentials or client data.

If two of three native edges are unhealthy, escalate rather than repeatedly
editing DNS. If all direct records are removed, stop and use the provider
selection/recovery process; do not point public DNS at a private node, etcd,
kubelet, or arbitrary port.

## Rollback and completion criteria

To roll back a failed provider cutover, first withdraw the provider VIP from
public DNS and wait for the approved DNS TTL. Restore the previously recorded
DNS-only backend A records only after confirming the direct edges are healthy.
For the API, keep the stable kubeconfig hostname and SAN if possible; reverting
clients to an IP is an emergency exception and must be tracked because it
reintroduces certificate and failover risk.

Issue #7 is operationally complete only after an authorized operator has:

- provisioned the provider VIP and recorded its private service ID;
- validated `k3s-api.belacca.com` in every API certificate and kubeconfig;
- cut application/API DNS to the single VIP with no backend A-record split
  brain;
- demonstrated withdrawal and recovery for one edge and one control-plane
  backend;
- measured and recorded convergence in the evidence artifact; and
- demonstrated that etcd, kubelet, overlay, Longhorn, metrics, SSH, and other
  internal ports remain unavailable from the public/provider-LB boundary.

Until then, leave the contract status and evidence status as pending and use
manual DNS removal. No repository-only test can substitute for this live
provider and failure-domain evidence.

## References

- [Kubernetes API health endpoints](https://kubernetes.io/docs/reference/using-api/health-checks/)
- [K3s server options (`--tls-san`)](https://docs.k3s.io/cli/server)
- [K3s cluster access and kubeconfig handling](https://docs.k3s.io/cluster-access)
- [HAProxy health checks and rise/fall behavior](https://www.haproxy.org/download/2.9/doc/configuration.txt)
