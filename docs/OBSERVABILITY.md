# Native production observability

The maintained observability implementation lives under
`clusters/belacca-production/observability/`. It is private, Flux-owned, and
bounded by resource, retention, sample, label, and NetworkPolicy controls.

Native Prometheus provides diagnostic target health and Pong/Flux recording
rules and forwards rule alerts to the private Alertmanager receiver. Flux
notification-controller also sends reconciliation events to Alertmanager;
Alertmanager groups and delivers configured pages through Telegram. External
status-repository SLO evidence is published separately by the GitHub-hosted
monitor; it is not scraped into Prometheus and native metrics do not substitute
for the external user-journey SLI.

## Current contracts

- Target health covers native Pong and Flux controllers.
- Metrics contain no room IDs, player names, addresses, tokens, request IDs, or
  other unbounded labels.
- Prometheus retention and storage are bounded and exceed the policy window.
- The monitoring surface is ClusterIP/private and has no public ingress.
- Missing external evidence is unknown, never success.
- Dashboard and Flux authenticated journeys remain pending until an
  operator-managed identity is provisioned.
- Independent cluster-down monitoring is deferred to platform issue #14.

Validate with `scripts/validate-observability.py` and
`scripts/extract-prometheus-config.py`; CI renders the native observability
Kustomization and runs the available Prometheus checks.
