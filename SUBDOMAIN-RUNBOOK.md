# Native production subdomain runbook

This runbook covers adding or changing a `*.belacca.com` hostname in the only
maintained production plane: native Flux under `clusters/belacca-production/`.

## Procedure

1. Obtain a narrowly scoped Cloudflare DNS token out of band. Never commit or
   print it.
2. Add or update DNS-only A records for all reviewed native edge addresses.
3. Add the HTTP redirect, HTTPS route, TLS certificate, and Service reference
   under `clusters/belacca-production/routing/`.
4. Keep credentials in the native out-of-band Secret contract.
5. Render and validate the native Kustomizations, commit, push, and reconcile
   Flux.
6. Verify DNS, certificate SANs, route behavior, authentication boundaries, and
   backend health from an external vantage point.

## Native boundaries

- Use the `belacca-native` Kubernetes context for native operations.
- Native Traefik terminates TLS; cert-manager uses Cloudflare DNS-01.
- Public application hosts use the reviewed native edge addresses.
- Operator hosts remain protected by Dex/OAuth2 Proxy and private Services.
- Do not expose etcd, kubelet, overlay, Longhorn, or arbitrary NodePorts.
- The final owner of every production object is native Flux, not a manual apply.

## Validation

```bash
kubectl config use-context belacca-native
kubectl kustomize clusters/belacca-production >/tmp/native-production-render.yaml
git diff --check
flux reconcile kustomization flux-system -n flux-system --with-source
```

Verify the route with external DNS and HTTPS checks, preserving redirect paths.
Do not include Secret values, tokens, private keys, or response bodies in
commits or evidence.
