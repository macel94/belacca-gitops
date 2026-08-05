# Flux notifications

[`../clusters/vmi3474918/notifications.yaml`](../clusters/vmi3474918/notifications.yaml)
defines two Flux `Alert` resources and one generic-webhook `Provider` in
`flux-system`:

- `platform-errors` forwards error events from all Flux GitRepositories,
  Kustomizations, and HelmReleases in `flux-system`.
- `platform-deployments` forwards only success/ready events from those same
  resource classes.
- `platform-webhook` uses the `generic` provider and reads the destination from
  the out-of-band Secret `flux-system/platform-notification-webhook`.

No endpoint, token, header, or Secret data is committed. The provider remains
unusable until an operator creates the Secret with the following runtime
contract:

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
schedule are operator-owned prerequisites. Create the Secret using a protected
secret manager or a private shell, for example:

```bash
kubectl -n flux-system create secret generic platform-notification-webhook \
  --from-literal=address='https://<approved-endpoint>' \
  --from-literal=token='<approved-token>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

The command is documentation only; do not put its real values in Git, shell
history, CI logs, or issue comments. If the receiving system needs a custom
header, put a `headers` key in the same Secret as described by the Flux
notification-controller API. The generic provider posts Flux event JSON and
supports HTTPS endpoints; test with a harmless staging/diagnostic event before
using it for paging.

## Verification

After the Secret exists in the target cluster:

```bash
kubectl -n flux-system get provider platform-webhook
kubectl -n flux-system describe provider platform-webhook
kubectl -n flux-system get alert platform-errors platform-deployments
kubectl -n flux-system logs deploy/notification-controller --since=10m
```

A missing Secret is an expected, visible prerequisite in an environment where
notifications have not yet been provisioned. It must not be “fixed” by adding a
fake Secret or a real endpoint to this repository.

## Notification hygiene

Alerts contain Flux object metadata and reconciliation messages. Receivers must
be configured to retain only the minimum operational data, restrict access, and
avoid forwarding Secret values or private application payloads. Review the
receiver and token after any incident involving notification logs.

Reference: <https://fluxcd.io/flux/components/notification/providers/> and
<https://fluxcd.io/flux/components/notification/alerts/>.
