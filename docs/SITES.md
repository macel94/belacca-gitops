# Supported native production platform sites

This is the canonical inventory of public sites and operator surfaces for
native production. The cluster is reconciled from `clusters/belacca-production/`
and publicly addressed through `169.58.143.41`, `169.58.143.42`, and
`169.58.97.73`. Host routing is owned by this repository and Cloudflare DNS-only
records contain all three native addresses.

## Native production public endpoints

| Host | Role | Access and behavior | Owner/source |
|---|---|---|---|
| `francesco.belacca.com` | Canonical personal site | Public static portfolio, reliability note, public status page, and `/health` | `macel94/francesco-belacca-site` |
| `belacca.com` | Apex alias | Permanent HTTPS redirect preserving the path | Native production routing |
| `www.belacca.com` | Apex `www` alias | Permanent HTTPS redirect preserving the path | Native production routing |
| `www.francesco.belacca.com` | Portfolio `www` alias | Permanent HTTPS redirect preserving the path | Native production routing |
| `pong.belacca.com` | Cloud Native Pong | Public multiplayer game, API, and WebSocket-compatible journey | `macel94/cloudnativepong` |
| `stats.belacca.com` | GoatCounter analytics | Public `/count`, `/count.js`, and `/status`; protected dashboard | Native GitOps analytics tree |
| `dashboard.belacca.com` | Headlamp operations dashboard | Protected OAuth2 Proxy, Dex, and Google route | Native GitOps Headlamp tree |
| `flux.belacca.com` | Flux Web UI | Protected Dex/Google operations route | Native GitOps Flux Web UI tree |
| `dex.belacca.com` | Dex operator alias | TLS-protected Dex route | Native GitOps Dex tree |

## Canonicalization

- `francesco.belacca.com` is the canonical portfolio origin.
- Portfolio aliases permanently redirect while preserving request paths.
- `pong.belacca.com` is the canonical Pong origin.
- Analytics collector paths remain public; its dashboard is protected.
- Dashboard, Flux, and Dex hosts are operator-facing routes, not public applications.

## DNS and monitoring

Each supported application hostname has DNS-only A records for the three native
edges. `k3s-api.belacca.com` uses the reviewed API addresses. Direct DNS
round-robin is not health-aware; remove an unhealthy address manually until a
health-aware VIP is provisioned. Native Traefik terminates TLS and cert-manager
uses Cloudflare DNS-01 with an out-of-band token.

The external status publisher checks the portfolio, Pong, analytics `/status`
and `/count`, `/count.js`, and portfolio aliases. The 99%/30d objective is
internal, not an SLA. `status.json` is current status evidence; `slo.json` is
rolling-window reliability evidence and remains non-reportable until a complete
valid window exists. Native Prometheus is private diagnostic telemetry.
