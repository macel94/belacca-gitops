# Supported native production platform sites

This is the canonical inventory of the public sites and operator surfaces for
**native production**. Native production is the three-server k3s cluster,
reconciled from `clusters/belacca-production/` and publicly addressed through
`169.58.143.41` and `169.58.143.42`. Host routing is owned by this repository;
Cloudflare DNS-only records contain both native addresses.

## Deployment boundary

- **Native production:** `clusters/belacca-production/`, with public edges on
  `169.58.143.41` and `169.58.143.42`.
- **Retired old production:** historical `k3d-pong` /
  `clusters/vmi3474918/` / `169.58.97.73`. Its Podman containers were removed
  after state migration and it is not a live public origin.
- Direct DNS round-robin is used instead of a health-aware load balancer.
  Operators must monitor both native edges and manually remove a failed A
  record if necessary.

## Native production public endpoints

| Host | Role | Access and behavior | Owner/source |
|---|---|---|---|
| [`francesco.belacca.com`](https://francesco.belacca.com/) | Native production canonical personal site | Public static portfolio, reliability note, public status page, and `/health` probe | `macel94/francesco-belacca-site` |
| [`belacca.com`](https://belacca.com/) | Native production apex alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Native production platform routing |
| [`www.belacca.com`](https://www.belacca.com/) | Native production apex `www` alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Native production platform routing |
| [`www.francesco.belacca.com`](https://www.francesco.belacca.com/) | Native production portfolio `www` alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Native production platform routing |
| [`pong.belacca.com`](https://pong.belacca.com/) | Native production Cloud Native Pong | Public multiplayer game, API, and WebSocket-compatible real-time journey; application-native WebTransport remains opt-in | `macel94/cloudnativepong` |
| [`stats.belacca.com`](https://stats.belacca.com/) | Native production GoatCounter analytics | `/count`, `/count.js`, and `/status` are public collector/status paths; the dashboard is protected by Dex/OAuth2 Proxy and then GoatCounter's own session | Native GitOps analytics tree |
| [`dashboard.belacca.com`](https://dashboard.belacca.com/) | Native production Headlamp operations dashboard | Protected by OAuth2 Proxy, Dex, and Google; not a public application | Native GitOps Headlamp tree |
| [`flux.belacca.com`](https://flux.belacca.com/) | Native production Flux Web UI | Protected native production Flux operations UI using Dex/Google authentication | Native GitOps Flux Web UI tree |
| [`dex.belacca.com`](https://dex.belacca.com/) | Native production Dex operator alias | TLS-protected Dex root handler; the issuer is path-scoped under `dashboard.belacca.com/oauth2/` | Native GitOps Dex routing |

The native production canonical portfolio, its three aliases, and Pong are
public user-facing routes or redirects. Native analytics exposes deliberately
public collector/status paths while its dashboard is protected. The remaining
dashboard, Flux, and Dex hosts are native production operator-facing routes or
aliases. No wildcard host or additional supported site is implied by the
native production configuration.

## Canonicalization in native production

- `https://francesco.belacca.com/` is the only canonical native production
  portfolio origin.
- `belacca.com`, `www.belacca.com`, and `www.francesco.belacca.com` return a
  permanent redirect to that origin and retain the request path.
- `https://pong.belacca.com/` is the only canonical native production Pong origin.
- The external status publisher currently validates the WebSocket-compatible
  journey. Application-native WebTransport is documented and implemented as an
  opt-in path, not as a deployed public ingress guarantee.
- `https://stats.belacca.com/` is both the native production analytics collector
  origin and the protected GoatCounter dashboard origin; its public paths must
  remain available without authentication.
- `dashboard.belacca.com`, `flux.belacca.com`, and `dex.belacca.com` are old
  production operator surfaces and must not be described as public application
  sites.

## Native production DNS

DNS is managed out of band at Cloudflare. Each application hostname and
`k3s-api.belacca.com` has DNS-only A records for both native edges:

```text
all supported application hosts  A 169.58.143.41
all supported application hosts  A 169.58.143.42
k3s-api.belacca.com             A 169.58.143.41
k3s-api.belacca.com             A 169.58.143.42
```

This direct DNS round-robin is not health-aware. Remove an unhealthy address
manually until a health-aware VIP or load balancer is provisioned. Native
Traefik terminates TLS and cert-manager uses Cloudflare DNS-01; the API token
is an out-of-band Kubernetes Secret and no credential belongs in Git.

## Native production monitoring coverage

The external status publisher runs outside the native cluster and currently
checks these public journeys:

- `francesco.belacca.com`: homepage and `/health`;
- `pong.belacca.com`: homepage, `/health`, room API, two-player
  WebSocket-compatible journey, and cleanup;
- `stats.belacca.com`: `/status`, a harmless `/count` collector probe, and
  `/count.js` availability; and
- portfolio aliases: permanent redirect and path preservation diagnostics.

The 99% availability objective is internal, per public service over 30 days,
with no SLA. Sanitized observations and `slo.json` are durable evidence, but
values remain not reportable until a complete valid 720-hour window exists.
Native Prometheus is private diagnostic telemetry, not the public SLO source.
The authenticated dashboard, Flux UI, and Dex alias remain unconfigured because
safe operator credentials are not provisioned for an external probe. See
[`macel94/belacca-status`](https://github.com/macel94/belacca-status) and its
[`POLICY.md`](https://github.com/macel94/belacca-status/blob/main/POLICY.md).

The separate controlled-drill recovery objective is P95 under six minutes; it
is not established by synthetic observations, capacity baselines, or internal
metrics. One-node failure drills and authenticated browser journeys remain
hardening work.
