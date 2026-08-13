# Native production notifications

Native production uses one central in-cluster Alertmanager notification
aggregation path:

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

The implementation uses separate diagnostic/default and actionable page
Telegram receivers. Both receivers preserve firing notifications. Only the
page receiver sends resolved notifications:

| Telegram class | Sources and route | Firing | Resolved |
|---|---|---:|---:|
| Diagnostic/default (`telegram-diagnostic`) | Flux `notificationClass=diagnostic`, Prometheus diagnostic labels such as `notification_class=capacity` or `backup`, and any unmatched/default alert | yes | **no** |
| Actionable page (`telegram-page`) | Flux `notificationClass=page` or `page-recovery`, and Prometheus `notification_class=page` | yes | **yes** |

Diagnostic health-check recoveries are deliberately suppressed because they
are internal context rather than operator-page incidents. This does not mute,
inhibit, delay, or weaken their firing notification. Page recovery notices
remain enabled so an actionable incident retains its recovery signal. The
explicit `page-recovery` route also keeps Flux recovery events in the page
receiver rather than allowing them to fall through to the diagnostic default.

The Alertmanager routing defaults remain:

- initial grouping delay: 30 seconds for page signals, 2 minutes for diagnostic signals;
- group interval: 5 minutes;
- repeat interval: 2 hours for page signals, 12 hours for diagnostic signals;
- grouping labels: `cluster`, `alertname`, `service`, `namespace`, and `name`;
- critical alerts inhibit matching warnings;
- Flux camelCase metadata and Prometheus snake_case labels are both routed;
- Alertmanager state is retained on the dedicated 1Gi Longhorn PVC.

This is a receiver-specific `send_resolved` policy, not a `repeat_interval`
change. Alertmanager route settings are inherited from the root unless a child
route overrides them; `send_resolved` belongs to each Telegram integration, so
the two receivers make the policy explicit without changing grouping or firing
routes. See the [official Alertmanager configuration reference](https://prometheus.io/docs/alerting/latest/configuration/)
for the route inheritance, grouping, and Telegram integration semantics.

The exact alert selection remains represented by the Flux `Alert` resources and
Prometheus rules in the production tree. This commit changes the checked-in
contract only; it does not claim deployment or live Telegram verification. The
existing notification evidence predates this receiver split and must not be
used as proof of the new behavior.

## Restore or tune the policy

To restore diagnostic resolved Telegram notifications, change only the
`send_resolved` value under `telegram-diagnostic` in
`clusters/belacca-production/observability/alertmanager-config.yaml` to
`true`, then run the validators and complete the verification matrix below.
To change which alerts are actionable, update the explicit Flux/Prometheus
classification and matching route together. Do not use `repeat_interval` as a
substitute for resolved-message suppression, and do not remove the page route,
inhibition rules, firing notifications, or readiness checks as a noise fix.

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

For a private, harmless verification matrix, submit one synthetic alert per
class and verify all of the following after reconciliation:

1. diagnostic firing reaches Telegram;
2. diagnostic resolution produces no Telegram delivery;
3. page firing reaches Telegram;
4. page resolution and the Flux page-recovery event retain Telegram delivery;
5. grouping and inhibition remain effective, firing delivery failures remain
   zero, and Alertmanager readiness/configuration endpoints remain healthy.

Use Alertmanager receiver-specific notification metrics and the private API to
confirm delivery/non-delivery; do not infer Telegram behavior from a local
configuration render or claim live verification without current evidence.
Flux recovery events are delivered as normal Flux events, so their exact
lifecycle semantics must be confirmed during the live matrix.
