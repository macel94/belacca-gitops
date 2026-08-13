# Native production observability runbook

## Scope and ownership

This runbook applies only to native production:
`clusters/belacca-production/`, cluster identity `belacca-native`. The tree at
Only `clusters/belacca-production/` is a maintained production monitoring target.
Flux owns the native child `native-observability`; it is private, diagnostic,
and intentionally has `prune: false` until the live resource and CNI checks are
completed.

The native slice is a single Prometheus Deployment with a private ClusterIP
Service. It has no Ingress, NodePort, LoadBalancer, public DNS name, or public
metrics route. Prometheus does not read the status Git repository. The external
runner and its durable sanitized history remain the independent SLO evidence
source.

## Inspecting native readiness and target health

Use the `belacca-native` context and a private operator path only. These commands
are inspection examples; do not apply generated output manually.

```text
kubectl config use-context belacca-native
kubectl -n flux-system get kustomization native-observability
kubectl -n observability get deploy,pod,svc,pvc,networkpolicy
kubectl -n observability port-forward service/prometheus-native 9090:9090
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:9090/api/v1/targets
```

A healthy Prometheus process (`/-/ready`) is not proof that a scrape target is
healthy. Inspect the private target view and confirm `up == 1` separately for:

- `native-pong-api-diagnostic` — aggregate Pong `/metrics` only;
- `native-flux-controllers-diagnostic` — the four Flux controller metrics
  endpoints; and
- `native-slo-evidence-boundary` — expected to be down until the external
  evidence adapter is deliberately provisioned.

A down or absent scrape is a diagnostic gap. It must not be turned into a good
SLO event.

## SLO evidence boundary

The machine-readable contract is
`clusters/belacca-production/observability/synthetic-contracts.json`. A future
private Flux-owned adapter may expose only:

- counter `belacca_slo_observation_events_total`;
- `service`: exactly `portfolio`, `pong`, or `analytics`;
- `outcome`: exactly `good` or `bad`; and
- one counter increment per valid hourly observation.

The adapter is **not deployed by this change**. Its target
`slo-evidence-adapter.observability.svc.cluster.local:8080` is an explicit,
private ingestion boundary and is expected to be absent/down. The adapter must
translate only the sanitized status evidence; it must never expose room IDs,
player names, client addresses, tokens, request IDs, URLs, response bodies, raw
errors, or other unbounded labels. Prometheus drops all labels except the bounded
allowlist before storage.

The recording rules define `good_events`, `total_events`, `data_coverage`,
`sli`, and `error_budget` over 30 days for each approved service. They expect
720 hourly slots. Missing, malformed, or partial evidence produces no numeric
SLI or error-budget series; it never counts as success. The rules require
exactly full coverage and at least one total event, so duplicate evidence also
cannot silently make a claim. A 99% target allows 1% bad events, or 7.2 hourly
slots, once a complete valid window exists.

Native Prometheus records diagnostic Pong/Flux signals and the SLO arithmetic
boundary, but it does not publish a public availability claim. The durable
external status repository remains authoritative for policy evidence until a
reviewed adapter and complete 720-slot window exist.

## Bounds and retention

| Resource | Bound |
| --- | --- |
| Prometheus replicas | 1 |
| CPU request/limit | 100m / 500m |
| Memory request/limit | 256Mi / 768Mi |
| Prometheus data PVC | Longhorn RWO, 5Gi requested |
| TSDB retention | 45 days and 4GiB, whichever is reached first |
| Temporary filesystem | 64Mi emptyDir |
| Pong scrape sample limit | 100 |
| Flux scrape sample limit | 500 |
| SLO-boundary scrape sample limit | 100 |
| Scrape/evaluation interval | 30 seconds |

The 45-day/4GiB bounds exceed the 30-day policy window without creating an
unbounded monitoring store. The PVC is retained for operator investigation;
operators must not delete or attach it to a second writer.

## Failure domains and limitations

- Direct DNS round-robin across the three native edges is not health-aware.
  Remove an unhealthy address manually until a health-aware VIP is available.
- The native Prometheus process, its Longhorn volume, Flux controllers, and
  application cluster share the native production failure domain. Native
  telemetry cannot independently prove an outage during a complete cluster
  failure.
- The external runner and Git history are outside the native cluster and can
  record a native outage, but the status page is hosted by the same cluster and
  may be unavailable while the cluster is down.
- NetworkPolicy manifests are rendered intent, not proof of CNI enforcement.
  Validate policy behavior with approved, non-destructive private checks.
- A working Prometheus readiness endpoint does not imply healthy Pong, Flux, or
  external evidence targets.
- Dashboard, Flux UI, and Dex authenticated synthetic checks remain proposed
  and are excluded from the three public-service SLO arithmetic series.

## Validation and operator follow-up

CI renders the native Kustomization and validates the extracted native rules and
config with the pinned Prometheus v3.13.2 `promtool` release and SHA-256 digest.
Local validation is:

```text
python3 scripts/validate-observability.py
python3 scripts/extract-prometheus-config.py
promtool check rules /tmp/native-prometheus.rules.yml
promtool check config /tmp/native-prometheus.yml
kubectl kustomize clusters/belacca-production/observability
```

Before treating the SLO recording rules as operational evidence, an operator must
provision and review a private adapter implementing the JSON contract, verify
its source and freshness behavior, test duplicate/malformed/missing slots, and
confirm its target health from the private Prometheus target view. Do not fake
that production evidence in this repository. The exact current limitation is
`deployment_status: contract-only/not-deployed` in the machine-readable
contract.
