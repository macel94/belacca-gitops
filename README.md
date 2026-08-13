# belacca.com GitOps platform

This repository is the cluster-level source of truth for the **native production**
platform: the three-server k3s cluster at `clusters/belacca-production/`,
publicly served through `169.58.143.41`, `169.58.143.42`, and `169.58.97.73`.

## Repository map

The following application and platform entries describe native production.

| Repository | Runtime | Public host | Native Flux path |
|---|---|---|---|
| [`cloudnativepong`](https://github.com/macel94/cloudnativepong) | Go lobby, Caddy gateway, Distroless rooms, WebSocket fallback, opt-in WebTransport | [pong.belacca.com](https://pong.belacca.com) | `./k8s/overlays/server` |
| [`francesco-belacca-site`](https://github.com/macel94/francesco-belacca-site) | Static Caddy portfolio | [francesco.belacca.com](https://francesco.belacca.com) | `./deploy` |
| GoatCounter | Self-hosted, cookie-free analytics | [stats.belacca.com](https://stats.belacca.com) | `./clusters/belacca-production/analytics` |

Native production has published application Flux paths for Pong, portfolio,
analytics, Dex, Headlamp, Flux Web, private Prometheus diagnostics, and native
Flux notification contracts. The native root and all child Kustomizations
reconcile successfully. Workloads remain private ClusterIP services behind
native Traefik; public traffic enters through the two direct host-network edges.
The external status repository is the source of the public 99%/30d SLO evidence;
native Prometheus is diagnostic and the notification destination remains out of
band/unprovisioned. The native one-node recovery contract, fail-closed evidence
ledger, and P95 validator are [`docs/NATIVE-FAILURE-DRILLS.md`](docs/NATIVE-FAILURE-DRILLS.md),
[`docs/NATIVE-DRILL-EVIDENCE.json`](docs/NATIVE-DRILL-EVIDENCE.json), and
`scripts/validate_native_drills.py`; live mutation remains owned by the
infrastructure repository.

## Why child GitRepositories instead of submodules?

Flux supports Git submodules, but application repositories are represented here
as independent Flux `GitRepository` objects. This keeps each project buildable
and releasable on its own, permits different credentials later if a project
becomes private, and lets changes in each source trigger its own Kustomization.
It also avoids requiring every developer and deployment tool to initialize a
nested checkout.

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
