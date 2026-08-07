# Old production Flux notifications

This document applies to **old production**: `k3d-pong`, reconciled from
`clusters/vmi3474918/`, with public address `169.58.97.73`.

**Native staging** is the separate `clusters/belacca-production/` tree for
three native servers, including `169.58.143.41` and `169.58.143.42`. It currently
contains the foundation plus manually staged Traefik only; no native
application notification resources are deployed. **Native cutover is not
started.**

[`../clusters/vmi3474918/notifications.yaml`](../clusters/vmi3474918/notifications.yaml)
defines two Flux `Alert` resources and one generic-webhook `Provider` in the
old production `flux-system` namespace:

- `platform-errors` forwards error events from all old production Flux
  GitRepositories, Kustomizations, and HelmReleases in `flux-system`.
- `platform-deployments` forwards only success/ready events from those same old
  production resource classes.
- `platform-webhook` uses the `generic` provider and reads the destination from
  the out-of-band old production Secret
  `flux-system/platform-notification-webhook`.

No endpoint, token, header, or Secret data is committed. The old production
provider remains unusable until an operator creates the Secret with the
following runtime contract:

```text
address: https://<operator-selected-notification-endpoint>
# Optional provider authentication, depending on the receiver:
token: <operator-managed-token>
# Optional HTTP headers encoded as a YAML map:
headers: |
  Authorization: <operator-managed-value>
```

Do not replace the placeholders above with a guessed destination. The address,
receiver type, authentication scheme, ownership, retention, and rotation
schedule are operator-owned old production prerequisites. Create the Secret
using a protected secret manager or a private shell, for example:

```bash
kubectl config use-context k3d-pong
kubectl -n flux-system create secret generic platform-notification-webhook \
  --from-literal=address='https://<approved-endpoint>' \
  --from-literal=token='<approved-token>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

The command is documentation only; do not put its real values in Git, shell
history, CI logs, or issue comments. If the old production receiving system
needs a custom header, put a `headers` key in the same Secret as described by
the Flux notification-controller API. The generic provider posts Flux event
JSON and supports HTTPS endpoints; test with a harmless non-paging diagnostic
event before using it for old production paging.

## Old production verification

After the Secret exists in old production:

```bash
kubectl config use-context k3d-pong
kubectl -n flux-system get provider platform-webhook
kubectl -n flux-system describe provider platform-webhook
kubectl -n flux-system get alert platform-errors platform-deployments
kubectl -n flux-system logs deploy/notification-controller --since=10m
```

A missing Secret is an expected, visible prerequisite in old production when
notifications have not yet been provisioned. It must not be “fixed” by adding
a fake Secret or a real endpoint to this repository.

Native staging is separate: `clusters/belacca-production/` targets three native
servers including `169.58.143.41` and `169.58.143.42`, and currently contains the
native foundation plus manually staged Traefik only, with no native
application notification contract. Native cutover is not started, so old
production notification checks must not be presented as native staging
coverage.

## Notification hygiene

Old production alerts contain Flux object metadata and reconciliation messages.
Receivers must be configured to retain only the minimum operational data,
restrict access, and avoid forwarding Secret values or private application
payloads. Review the receiver and token after any incident involving old
production notification logs.

References: <https://fluxcd.io/flux/components/notification/providers/> and
<https://fluxcd.io/flux/components/notification/alerts/>.
