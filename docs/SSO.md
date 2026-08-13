# Native production platform SSO contract

This contract applies only to native production: the three-server k3s cluster
reconciled from `clusters/belacca-production/` with public edges at
`169.58.143.41`, `169.58.143.42`, and `169.58.97.73`. Dex is the shared OpenID
Connect broker for Flux Web, Headlamp, and the analytics dashboard.

The canonical issuer is `https://dashboard.belacca.com/oauth2`; the intended
administrator is `belakkuz@gmail.com`. Native services use private ClusterIP
backends, OAuth2 Proxy where required, and out-of-band Secrets. No credentials,
tokens, or cookie values belong in Git.

## Native production endpoints

| Endpoint | SSO path | Backend authorization |
|---|---|---|
| `https://flux.belacca.com/` | Flux Web OAuth2/OIDC through Dex and Google | `flux-web-admin` |
| `https://dashboard.belacca.com/` | OAuth2 Proxy through Dex and Google to Headlamp | Fixed native backend ServiceAccount |
| `https://stats.belacca.com/` | Protected dashboard route; public collector paths bypass auth | GoatCounter application session |
| `https://dex.belacca.com/` | Native Dex endpoint | Operator route |

Headlamp uses the supported identity-aware proxy mode with a fixed backend
ServiceAccount. This is shared-admin access, not per-user Kubernetes OIDC/RBAC
impersonation. GoatCounter retains its own application session after the outer
proxy gate.

## Native validation

```bash
kubectl config use-context belacca-native
kubectl kustomize clusters/belacca-production >/tmp/native-production-platform-render.yaml
kubectl apply --dry-run=server -f /tmp/native-production-platform-render.yaml
flux reconcile kustomization flux-system -n flux-system --with-source
```

Never print Secret data, OAuth tokens, cookie values, Dex signing state, or
GoatCounter passwords in native production output or evidence.
