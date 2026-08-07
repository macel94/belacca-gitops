# Supported old production platform sites

This is the canonical inventory of the public sites and operator surfaces for
**old production**. Old production is the existing `k3d-pong` cluster,
reconciled from `clusters/vmi3474918/` and publicly addressed at
`169.58.97.73`. Host routing is owned by this repository and reconciled to that
old production cluster by Flux.

## Deployment boundary

- **Old production:** `k3d-pong` / `clusters/vmi3474918/` / `169.58.97.73`.
  The public endpoints and monitoring claims in this document apply here.
- **Native staging:** `clusters/belacca-production/`, targeting three native
  servers including `169.58.143.41` and `169.58.143.42`. It currently has
  the cluster foundation plus manually staged Traefik only. It has no deployed
  native applications or supported public site inventory.
- **Native cutover:** **not started**. Native staging must not be treated as a
  second public origin for any hostname below.

## Old production public endpoints

| Host | Role | Access and behavior | Owner/source |
|---|---|---|---|
| [`francesco.belacca.com`](https://francesco.belacca.com/) | Old production canonical personal site | Public static portfolio, reliability note, public status page, and `/health` probe | `macel94/francesco-belacca-site` |
| [`belacca.com`](https://belacca.com/) | Old production apex alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Old production platform routing |
| [`www.belacca.com`](https://www.belacca.com/) | Old production apex `www` alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Old production platform routing |
| [`www.francesco.belacca.com`](https://www.francesco.belacca.com/) | Old production portfolio `www` alias | Permanent HTTPS redirect to `https://francesco.belacca.com/`, preserving the path | Old production platform routing |
| [`pong.belacca.com`](https://pong.belacca.com/) | Old production Cloud Native Pong | Public multiplayer game, API, and WebSocket-compatible real-time journey; application-native WebTransport remains opt-in | `macel94/cloudnativepong` |
| [`stats.belacca.com`](https://stats.belacca.com/) | Old production GoatCounter analytics | `/count`, `/count.js`, and `/status` are public collector/status paths; the dashboard is protected by Dex/OAuth2 Proxy and then GoatCounter's own session | Old production GitOps analytics tree |
| [`dashboard.belacca.com`](https://dashboard.belacca.com/) | Old production Headlamp operations dashboard | Protected by OAuth2 Proxy, Dex, and Google; not a public application | Old production GitOps Headlamp tree |
| [`flux.belacca.com`](https://flux.belacca.com/) | Old production Flux Web UI | Protected old production Flux operations UI using Dex/Google authentication | Old production GitOps Flux Web UI tree |
| [`dex.belacca.com`](https://dex.belacca.com/) | Old production Dex operator alias | TLS-protected redirect alias to `https://dashboard.belacca.com/oauth2/`; it is not a separate dashboard | Old production GitOps Dex routing |

The old production canonical portfolio, its three aliases, and Pong are public
user-facing routes or redirects. Old production analytics exposes only
deliberately public collector/status paths while its dashboard is protected.
The remaining dashboard, Flux, and Dex hosts are old production operator-facing
routes or aliases. No wildcard host or additional supported old production site
is implied by the old production cluster configuration.

Native staging has no public endpoint table yet. In particular, the presence of
native foundation resources, encrypted Secret interfaces, or manually staged
Traefik does not mean that a native portfolio, Pong, analytics, dashboard, Flux
Web UI, or Dex application is deployed.

## Canonicalization in old production

- `https://francesco.belacca.com/` is the only canonical old production
  portfolio origin.
- `belacca.com`, `www.belacca.com`, and `www.francesco.belacca.com` return a
  permanent redirect to that origin and retain the request path.
- `https://pong.belacca.com/` is the only canonical old production Pong origin.
- The old production Pong synthetic currently validates the WebSocket-compatible
  journey. Application-native WebTransport is documented and implemented as an
  opt-in path, not as a deployed public ingress guarantee.
- `https://stats.belacca.com/` is both the old production analytics collector
  origin and the protected GoatCounter dashboard origin; its public paths must
  remain available without authentication.
- `dashboard.belacca.com`, `flux.belacca.com`, and `dex.belacca.com` are old
  production operator surfaces and must not be described as public application
  sites.

## Old production DNS

DNS is managed out of band at Cloudflare. Each old production hostname below
must resolve to `169.58.97.73` before normal HTTPS traffic and certificate
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
dex.belacca.com              A 169.58.97.73
```

Use DNS-only records because old production Traefik terminates TLS and obtains
certificates through the committed Cloudflare DNS-01 configuration. The
Cloudflare API token is an out-of-band Kubernetes Secret; no DNS credential
belongs in Git. The repeatable old production DNS, ACME, routing, and rollback
procedure is in [`SUBDOMAIN-RUNBOOK.md`](../SUBDOMAIN-RUNBOOK.md).

Native staging has no old production DNS records and no supported public DNS
record set. Do not point any hostname above at the native `.41` or `.42` hosts
before a separately reviewed native cutover.

## Old production monitoring coverage

The external status publisher currently probes only these old production
application surfaces:

- `francesco.belacca.com` homepage and `/health`;
- `pong.belacca.com` homepage, `/health`, API, room lifecycle, and two-player
  WebSocket-compatible journey; and
- `stats.belacca.com/status` plus the old production analytics endpoint
  contract.

The old production redirect aliases are verified as routing behavior, not as
independent applications. The old production authenticated dashboard, Flux UI,
and Dex alias are not part of the automated public status claim because they
require operator credentials. See
[`macel94/belacca-status`](https://github.com/macel94/belacca-status) and its
[`POLICY.md`](https://github.com/macel94/belacca-status/blob/main/POLICY.md).

Nothing in this monitoring list is a native staging availability claim. Native
monitoring and application checks belong to a future, separately reviewed
cutover plan.
