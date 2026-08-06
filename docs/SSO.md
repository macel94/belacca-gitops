# Platform SSO contract

The platform uses **Dex** as the shared OpenID Connect broker. Dex federates the
existing Google OAuth application, and each application has a separate Dex
client. The canonical path-scoped issuer is
`https://dashboard.belacca.com/oauth2`; `dex.belacca.com` is a TLS-protected
redirect alias. The intended administrator is `belakkuz@gmail.com`.

## Public endpoints

| Endpoint | SSO path | Backend authorization |
|---|---|---|
| `https://flux.belacca.com/` | Flux Web UI OAuth2/OIDC → Dex (`https://dashboard.belacca.com/oauth2`) → Google | `flux-web-admin` for the Google email claim |
| `https://dashboard.belacca.com/` | OAuth2 Proxy (`/headlamp-auth`) → Dex (`/oauth2`) → Google | Headlamp's fixed in-cluster backend ServiceAccount is bound to `cluster-admin`; the proxy allowlist contains only the intended email |
| `https://stats.belacca.com/` | OAuth2 Proxy → Dex (`https://dashboard.belacca.com/oauth2`) → Google for the dashboard UI | A higher-priority direct Ingress sends public `/count`, `/count.js`, and `/status` paths to GoatCounter; dashboard pages still require its own application session cookie |
| `https://dex.belacca.com/` | Redirect alias to the canonical Dex issuer | Not an application dashboard |

The current Headlamp deployment uses its in-cluster mode, which authenticates
Kubernetes API calls with one pod ServiceAccount. It cannot turn the browser's
Dex identity into Kubernetes API impersonation without changing the K3s API
server's OIDC configuration. The separate `headlamp-authenticated-admin`
ClusterRoleBinding therefore makes the backend administrative, while the public
Dex/OAuth2 Proxy allowlist is the user authentication boundary. Do not expose
Headlamp's ClusterIP or remove the network policy as a workaround.

GoatCounter does not consume `X-Forwarded-User` or OAuth2 Proxy identity headers;
its upstream dashboard authentication is a password-backed `key` cookie. The
Dex proxy protects the public hostname and restricts who can reach that login,
but it does not replace GoatCounter's own application session. Keep the
GoatCounter account email aligned with `belakkuz@gmail.com` if one-person admin
ownership is desired, and retain its password in the out-of-band Secret.

## Kubernetes Secret contract

Create these Secrets out of band before reconciling the child Kustomizations.
The names and keys are GitOps API contracts; values must never be committed:

| Namespace | Secret | Required keys |
|---|---|---|
| `dex` | `dex-google-oauth` | `client-id`, `client-secret` (the existing Google OAuth app) |
| `dex` | `dex-client-secrets` | `flux-web-client-secret`, `headlamp-client-secret`, `stats-client-secret` |
| `flux-system` | `flux-web-client` | `client-id` (`flux-web`), `client-secret` |
| `headlamp` | `headlamp-dex-oauth` | `client-id` (`headlamp`), `client-secret`, `cookie-secret` |
| `analytics` | `analytics-dex-oauth` | `client-id` (`stats`), `client-secret`, `cookie-secret` |

The OAuth2 Proxy cookie secrets should be generated with a cryptographically
secure random generator. Rotate a client or cookie secret by updating the
out-of-band Secret and reconciling the owning HelmRelease; expect existing
sessions to expire.

## Google OAuth application

The existing Google OAuth application already authorizes the callback Dex uses
for its Google connector:

```text
https://dashboard.belacca.com/oauth2/callback
```

Dex then returns each relying party to its own callback (`flux.belacca.com`,
`dashboard.belacca.com/headlamp-auth`, or `stats.belacca.com`). The old direct
Google OAuth2 Proxy path is no longer the active Headlamp path. Dex's Google
connector uses the existing client ID/secret and requests only profile/email
identity data; no Google Workspace service-account group delegation is needed
because RBAC is bound directly to the email claim.

## Validation

```bash
kubectl kustomize clusters/vmi3474918 >/tmp/platform-render.yaml
kubectl apply --dry-run=server -f /tmp/platform-render.yaml
kubectl -n dex get secret dex-google-oauth dex-client-secrets
kubectl -n flux-system get secret flux-web-client
kubectl -n headlamp get secret headlamp-dex-oauth
kubectl -n analytics get secret analytics-dex-oauth
curl -fsS https://dashboard.belacca.com/oauth2/.well-known/openid-configuration
flux reconcile kustomization dex -n flux-system --with-source
flux reconcile kustomization flux-web -n flux-system --with-source
flux reconcile kustomization belacca-routing -n flux-system --with-source
```

Never print Secret data, OAuth tokens, cookie values, Dex signing state, or
GoatCounter passwords in command output or incident evidence.
