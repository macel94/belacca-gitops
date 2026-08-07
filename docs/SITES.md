# Supported platform sites

This is the canonical inventory of the public sites and operator surfaces for
the Belacca platform. Host routing is owned by this repository and reconciled
to the `k3d-pong` cluster by Flux.

## Public endpoints

| Host | Role | Access and behavior | Owner/source |
|---|---|---|---|
| [`francesco.belacca.com`](https://francesco.belacca.com/) | Canonical personal site | Public static portfolio, reliability note, public status page, and `/health` probe | `macel94/francesco-belacca-site` |
| [`belacca.com`](https://belacca.com/) | Apex alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Platform routing |
| [`www.belacca.com`](https://www.belacca.com/) | Apex `www` alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Platform routing |
| [`www.francesco.belacca.com`](https://www.francesco.belacca.com/) | Portfolio `www` alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Platform routing |
| [`pong.belacca.com`](https://pong.belacca.com/) | Cloud Native Pong | Public multiplayer game, API, and WebSocket-compatible real-time journey; native WebTransport remains opt-in | `macel94/cloudnativepong` |
| [`stats.belacca.com`](https://stats.belacca.com/) | GoatCounter analytics | `/count`, `/count.js`, and `/status` are public collector/status paths; the dashboard is protected by Dex/OAuth2 Proxy and then GoatCounter's own session | GitOps analytics tree |
| [`dashboard.belacca.com`](https://dashboard.belacca.com/) | Headlamp operations dashboard | Protected by OAuth2 Proxy, Dex, and Google; not a public application | GitOps Headlamp tree |
| [`flux.belacca.com`](https://flux.belacca.com/) | Flux Web UI | Protected Flux operations UI using Dex/Google authentication | GitOps Flux Web UI tree |
| [`dex.belacca.com`](https://dex.belacca.com/) | Dex operator alias | TLS-protected redirect alias to `https://dashboard.belacca.com/oauth2/`; it is not a separate dashboard | GitOps Dex routing |

The canonical portfolio, its three aliases, and Pong are public user-facing
routes or redirects. Analytics exposes only deliberately public collector/status
paths while its dashboard is protected. The remaining dashboard, Flux, and Dex
hosts are operator-facing routes or aliases. No wildcard host or additional
supported public site is implied by the cluster configuration.

## Canonicalization

- `https://francesco.belacca.com/` is the only canonical portfolio origin.
- `belacca.com`, `www.belacca.com`, and `www.francesco.belacca.com` return a
  permanent redirect to that origin and retain the request path.
- `https://pong.belacca.com/` is the only canonical Pong origin.
- The public Pong synthetic currently validates the WebSocket-compatible journey. WebTransport is documented and implemented as an opt-in path, not as a deployed public ingress guarantee.
- `https://stats.belacca.com/` is both the analytics collector origin and the
  protected GoatCounter dashboard origin; its public paths must remain available
  without authentication.
- `dashboard.belacca.com`, `flux.belacca.com`, and `dex.belacca.com` are
  operator surfaces and must not be described as public application sites.

## DNS

DNS is managed out of band at Cloudflare. Each hostname below must resolve to
the cluster public address before normal HTTPS traffic and certificate
validation can work:

```text
belacca.com                 A 169.58.97.73
www.belacca.com             A 169.58.97.73
francesco.belacca.com       A 169.58.97.73
www.francesco.belacca.com   A 169.58.97.73
pong.belacca.com            A 169.58.97.73
stats.belacca.com           A 169.58.97.73
dashboard.belacca.com       A 169.58.97.73
flux.belacca.com            A 169.58.97.73
dex.belacca.com             A 169.58.97.73
```

Use DNS-only records because Traefik terminates TLS and obtains certificates
through the committed Cloudflare DNS-01 configuration. The Cloudflare API token
is an out-of-band Kubernetes Secret; no DNS credential belongs in Git. The
repeatable DNS, ACME, routing, and rollback procedure is in
[`SUBDOMAIN-RUNBOOK.md`](../SUBDOMAIN-RUNBOOK.md).

## Monitoring coverage

The external status publisher currently probes only these application surfaces:

- `francesco.belacca.com` homepage and `/health`;
- `pong.belacca.com` homepage, `/health`, API, room lifecycle, and two-player
  WebSocket-compatible journey; and
- `stats.belacca.com/status` plus the analytics endpoint contract.

The redirect aliases are verified as routing behavior, not as independent
applications. The authenticated dashboard, Flux UI, and Dex alias are not part
of the automated public status claim because they require operator credentials.
See [`macel94/belacca-status`](https://github.com/macel94/belacca-status) and its
[`POLICY.md`](https://github.com/macel94/belacca-status/blob/main/POLICY.md).
