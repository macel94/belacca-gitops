# Native production platform SSO contract

## Deployment vocabulary and scope

This SSO contract applies to **native production**: the three-server k3s
cluster reconciled from `clusters/belacca-production/`, with public edges at
`169.58.143.41` and `169.58.143.42`. The platform uses **Dex** as the shared
OpenID Connect broker. Dex federates the existing Google OAuth application,
and each native application has a separate Dex client. The canonical
path-scoped issuer is `https://dashboard.belacca.com/oauth2`; `dex.belacca.com`
is a native production TLS-protected Dex endpoint. The intended administrator
is `belakkuz@gmail.com`.

The former k3d environment on `.73` is retired historical reference only.

## Native production public endpoints

| Endpoint | SSO path | Backend authorization |
|---|---|---|
| `https://flux.belacca.com/` | Native production Flux Web UI OAuth2/OIDC → Dex (`https://dashboard.belacca.com/oauth2`) → Google | `flux-web-admin` for the Google email claim |
| `https://dashboard.belacca.com/` | Native production OAuth2 Proxy (`/headlamp-auth`) → Dex (`/oauth2`) → Google → Headlamp identity-aware proxy headers | Headlamp's fixed in-cluster backend ServiceAccount is bound to `cluster-admin`; Headlamp `proxy-auth` is enabled and the proxy allowlist contains only the intended email |
| `https://stats.belacca.com/` | Native production OAuth2 Proxy → Dex (`https://dashboard.belacca.com/oauth2`) → Google for the dashboard UI | A higher-priority direct Ingress sends public `/count`, `/count.js`, and `/status` paths to native GoatCounter; dashboard pages still require its own application session cookie |
| `https://dex.belacca.com/` | Native production Dex endpoint | Not an application dashboard |

The native production Headlamp deployment uses its supported identity-aware proxy
mode. OAuth2 Proxy authenticates the browser and injects trusted identity
headers; Headlamp's `proxy-auth` flag consumes those headers and bypasses its
internal login screen. Kubernetes API calls use the mounted in-cluster
ServiceAccount token because `unsafeUseServiceAccountToken` is enabled. The
separately named `headlamp-authenticated-admin` ClusterRoleBinding therefore
makes that shared backend administrative. This is intentionally shared-admin
access, not per-user Kubernetes OIDC/RBAC impersonation. Do not expose
Headlamp's native production ClusterIP, weaken the network policy, or trust
client-supplied identity headers.

GoatCounter does not consume `X-Forwarded-User`, `X-Forwarded-Email`, or
OAuth2 Proxy identity headers; its upstream dashboard authentication is a
password-backed `key` cookie. The native production Dex proxy protects the public
hostname and restricts who can reach that login, but it does not replace
GoatCounter's own application session. This deliberate two-step boundary
remains because the self-hosted GoatCounter release has no supported OIDC or
trusted-header SSO configuration. Keep the GoatCounter account email aligned
with `belakkuz@gmail.com` if one-person admin ownership is desired, and retain
its password in the out-of-band native production Secret.

## Supported native production integration basis

The native production Headlamp route follows Headlamp's documented identity-aware
proxy integration: OAuth2 Proxy supplies trusted identity headers, Headlamp
enables `proxy-auth`, and the in-cluster ServiceAccount is used for backend
Kubernetes API access. This is a shared backend identity by design; per-user
Kubernetes OIDC/RBAC would require configuring the native production K3s API server
to validate Dex tokens and changing the authorization model.

The native production GoatCounter route intentionally stops at the outer Dex/
OAuth2 Proxy gate and then uses GoatCounter's own password-backed application
session. The self-hosted release has no supported OIDC or trusted
identity-header bridge, so we do not claim end-to-end Google SSO for the native
production analytics dashboard.

Official references:

- [Headlamp identity-aware proxy](https://headlamp.dev/docs/latest/installation/in-cluster/identity-aware-proxy/)
- [Headlamp OIDC](https://headlamp.dev/docs/latest/installation/in-cluster/oidc/)
- [OAuth2 Proxy configuration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/)
- [Flux Web UI SSO with Dex](https://fluxoperator.dev/docs/web-ui/sso-dex/)
- [Kubernetes OIDC authentication](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#openid-connect-tokens)
- [GoatCounter self-hosting](https://github.com/arp242/goatcounter/blob/release-2.7/README.md)

## Native production Kubernetes Secret contract

Create these Secrets out of band before reconciling the native production child
Kustomizations. The names and keys are native production GitOps API contracts;
values must never be committed:

| Namespace | Secret | Required keys |
|---|---|---|
| `dex` | `dex-google-oauth` | `client-id`, `client-secret` (the existing Google OAuth app) |
| `dex` | `dex-client-secrets` | `flux-web-client-secret`, `headlamp-client-secret`, `stats-client-secret` |
| `flux-system` | `flux-web-client` | `client-id` (`flux-web`), `client-secret` |
| `headlamp` | `headlamp-dex-oauth` | `client-id` (`headlamp`), `client-secret`, `cookie-secret` |
| `analytics` | `analytics-dex-oauth` | `client-id` (`stats`), `client-secret`, `cookie-secret` |

The native production OAuth2 Proxy cookie secrets should be generated with a
cryptographically secure random generator. Rotate a client or cookie secret by
updating the out-of-band Secret and reconciling the owning native production
HelmRelease; expect existing sessions to expire.

## Native production Google OAuth application

The existing Google OAuth application already authorizes the callback Dex uses
for its native production Google connector:

```text
https://dashboard.belacca.com/oauth2/callback
```

Dex then returns each native production relying party to its own callback
(`flux.belacca.com`, `dashboard.belacca.com/headlamp-auth`, or
`stats.belacca.com`). The old direct Google OAuth2 Proxy path is no longer the
active native production Headlamp path. Headlamp now uses the supported proxy-auth
header integration after OAuth2 Proxy has completed the Dex flow. Dex's Google
connector uses the existing client ID/secret and requests only profile/email
identity data; no Google Workspace service-account group delegation is needed
because the single backend identity is gated by the proxy email allowlist.

## Native production validation

The following commands validate native production only:

```bash
kubectl config use-context belacca-native
kubectl kustomize clusters/belacca-production >/tmp/old-production-platform-render.yaml
kubectl apply --dry-run=server -f /tmp/old-production-platform-render.yaml
kubectl -n dex get secret dex-google-oauth dex-client-secrets
kubectl -n flux-system get secret flux-web-client
kubectl -n headlamp get secret headlamp-dex-oauth
kubectl -n analytics get secret analytics-dex-oauth
curl -fsS https://dashboard.belacca.com/oauth2/.well-known/openid-configuration
flux reconcile kustomization dex -n flux-system --with-source
flux reconcile kustomization flux-web -n flux-system --with-source
flux reconcile kustomization flux-system -n flux-system --with-source
flux reconcile kustomization native-headlamp -n flux-system --with-source
flux reconcile kustomization native-flux-web -n flux-system --with-source
```

Never print Secret data, OAuth tokens, cookie values, Dex signing state, or
GoatCounter passwords in native production command output or incident evidence.
This validation block does not replace an authenticated browser journey.
