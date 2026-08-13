# Native production notifications

Native production uses one central in-cluster Alertmanager notification aggregation path:

```text
Flux events + Prometheus alerts
  -> Alertmanager (observability/alertmanager-native)
  -> Telegram Bot API
```

Alertmanager is the lightweight CNCF Prometheus component responsible for
routing, grouping, deduplication, inhibition, repeat intervals, and resolved
notifications. Flux sends its error/info events to Alertmanager using Flux's
official `alertmanager` Provider. Prometheus sends rule alerts to the same
Alertmanager service.

The runtime Secret is intentionally provisioned out of band:

- Namespace: `observability`
- Name: `alertmanager-telegram`
- Keys: `bot-token`, `chat-id`

No Telegram token, chat ID, or plaintext Secret belongs in Git. Do not create
an empty placeholder Secret: Alertmanager should not appear operational until
the actual destination is available.

## Routing policy

The implementation uses separate diagnostic and page lanes. The central receiver pages the operator for persistent or high-impact signals,
including Flux reconciliation failures, failed production Kustomizations or
HelmReleases, confirmed routing/storage impact, stale or failed backups, and
SLO signals when their independent source is available. It sends recovery
notifications for previously firing alerts.

Ordinary successful deployments, isolated low-level warnings, and transient
conditions are grouped or routed as diagnostic notifications rather than
immediate pages. Alertmanager's current defaults are:

- initial grouping delay: 30 seconds for page signals, 2 minutes for diagnostic signals;
- group interval: 5 minutes;
- repeat interval: 2 hours for page signals, 12 hours for diagnostic signals;
- resolved notifications enabled for Prometheus alerts;
- critical alerts inhibit matching warnings;
- Flux camelCase metadata and Prometheus snake_case labels are both routed;
- Alertmanager state is retained on the dedicated 1Gi Longhorn PVC.

The exact alert selection remains represented by the Flux `Alert` resources and
Prometheus rules in the production tree. This is not a claim that the live
Telegram destination has been tested: an operator must provision the Secret,
verify the native context, reconcile, and run the harmless delivery matrix.

## External monitoring is intentionally deferred

The in-cluster path cannot notify when the entire cluster, Kubernetes API,
Flux, Alertmanager, or node network is unavailable. Independent external
monitoring is deliberately out of scope for this implementation and tracked
separately in the platform follow-up issue. It must not be represented as
operational until an external owner, destination, probe, and recovery test are
approved.

## Verification

After the Secret is provisioned, verify without printing Secret data:

```sh
kubectl --context belacca-native -n observability get secret alertmanager-telegram
kubectl --context belacca-native -n observability get deploy,pod,svc alertmanager-native
kubectl --context belacca-native -n flux-system get provider,alert
kubectl --context belacca-native -n observability logs deploy/alertmanager-native --since=10m
```

Run a harmless diagnostic reconciliation event, confirm one Telegram delivery,
then verify grouping, duplicate suppression, resolved delivery for Prometheus
alerts, and the Alertmanager readiness/config endpoints through a private
operator path. Flux recovery events are delivered as normal Flux events; their
exact resolution semantics must be confirmed during the live matrix.
