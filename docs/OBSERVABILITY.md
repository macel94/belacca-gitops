# Old production observability contract

## Deployment vocabulary and boundary

This document describes the staged observability component for **old
production**: the existing `k3d-pong` cluster, reconciled from
`clusters/vmi3474918/` and publicly addressed at `169.58.97.73`.

**Native staging** is the separate `clusters/belacca-production/` tree for
three native servers, including `169.58.143.41` and `169.58.143.42`.
Native staging currently contains the foundation plus manually staged Traefik
only. It has no native Prometheus, application metrics targets, dashboards, or
native application workloads. **Native cutover is not started.** Do not use a
native staging render as evidence of old production observability or native
application deployment.

## Current old production implementation

The old production cluster tree contains an opt-in, private Prometheus collector
under `clusters/vmi3474918/observability/`.

- Prometheus `v3.13.2` is pinned by the verified multi-architecture image digest.
- It is a plain Deployment, not a Prometheus Operator installation.
- It has no public Ingress, NodePort, or LoadBalancer.
- It stores at most seven days and 2 GB in an `emptyDir` volume.
- It runs one replica because this is an old production single-host
  demonstration layer, not a highly available monitoring service.
- It scrapes the old production Pong API and old production Flux controller
  metrics through explicit static service targets.
- It has no Kubernetes Secret access and no application labels containing room
  IDs, player names, IP addresses, or request contents.
- The Prometheus API is allowed only from the old production private Headlamp
  namespace by the checked-in policy. Use a private port-forward after runtime
  validation.

The old production Flux `observability` Kustomization has `prune: false`
intentionally. This is an opt-in/staged component: validate resource usage and
CNI connectivity before considering a future ownership/pruning change. The old
production platform root has `prune: true` after ownership/inventory
verification; protected old production PVC behavior is unchanged.

`synthetic-contracts.json` is the machine-readable external-check contract for
old production portfolio, Pong, analytics, and authenticated dashboard
journeys. The Pong repository now runs the canonical old production public
journey on a scheduled GitHub Actions workflow; the other service checks still
require their own external runners. The contract contains no credentials or
collected results. `dashboard.json` is a private dashboard query/panel
definition; it is source material, not proof that Grafana is installed or that
the queries currently have data.

This repository does **not** currently install Grafana, Prometheus Operator,
blackbox-exporter, OpenTelemetry Collector, or a public metrics route in old
production. Those are separate follow-up changes requiring CRD/chart/runtime
validation. The public site status page remains externally published and
unknown by default; Prometheus is not treated as its own external status
authority.

## Old production scrape contract

The old production application contract is:

```text
GET http://pong-api.pong.svc.cluster.local:8080/metrics
Content-Type: text/plain; version=0.0.4; charset=utf-8
```

Metric names are fixed and have no labels. Current groups include:

- `pong_http_requests_total`
- `pong_http_requests_success_total`
- `pong_http_requests_failure_total`
- `pong_rooms_active`
- `pong_rooms_waiting`
- `pong_rooms_playing`
- `pong_websockets_active` (the compatibility WebSocket path)
- `pong_webtransports_active` (optional application-native HTTP/3 path)
- `pong_webtransport_*`
- `pong_sqlite_*`
- `pong_room_*`
- `pong_websocket_*`
- `pong_admission_*`

Do not add room ID, player name, client address, URL, or arbitrary error text as
metric labels. Use aggregate counters or bounded log/evidence fields instead.
The current sample limit for the old production Pong scrape is 100.

Old production Flux controllers expose metrics on their existing internal HTTP
service port; the collector uses a sample limit of 500 for that target group. A
missing Flux metric series is a diagnostic gap, not proof that old production
reconciliation is healthy.

## Old production rules and dashboards

`prometheus.rules.yml` contains proposed recording rules for:

- old production Pong request/error rates
- active rooms, WebSocket compatibility sessions, and optional application-
native WebTransport sessions
- old production Flux Ready-condition failures
- fast and slow candidate burn-rate alerts

The rules are warning/diagnostic only until an external SLI source, owner, alert
destination, and measured SLO are approved. The candidate alerts must not be
represented publicly as achieved old production availability.

Useful initial dashboard panels, whether queried through a future private old
production Grafana or old production Prometheus itself, are:

```promql
sum(rate(pong_http_requests_total[5m]))
sum(rate(pong_http_requests_failure_total[5m]))
pong_rooms_active
pong_rooms_waiting
pong_rooms_playing
pong_websockets_active
pong_webtransports_active
sum(rate(pong_websocket_proxy_dial_failure_total[5m]))
sum(rate(pong_webtransport_proxy_dial_failure_total[5m]))
sum(rate(gotk_reconcile_condition{status="False",type="Ready"}[5m]))
```

If a future old production dashboard is installed, keep it private through
Headlamp/port-forward or an identity-aware route. Do not expose Prometheus or
Grafana directly on an old production public hostname. Native staging has no
such dashboard claim.

## Old production runtime validation checklist

Before treating old production observability as deployed and healthy:

```bash
kubectl config use-context k3d-pong
kubectl kustomize clusters/vmi3474918/observability >/tmp/old-production-observability.yaml
kubectl apply --dry-run=server -f /tmp/old-production-observability.yaml
flux reconcile kustomization observability -n flux-system --with-source
kubectl -n observability get deploy,pod,svc,networkpolicy
kubectl -n observability port-forward service/prometheus 9090:9090
curl -fsS http://127.0.0.1:9090/-/ready
```

Then verify from the old production Prometheus target page that the Pong and
Flux jobs are healthy, and use a non-destructive connectivity check to confirm
the old production observability → Pong allow rule. Do not widen policies to
`0.0.0.0/0` as a shortcut. If resource pressure or CNI incompatibility
appears, suspend the old production `observability` Kustomization and revert
this staged component through old production GitOps; do not delete old
production application PVCs or the cluster.

For native staging, a Kustomize render only confirms the foundation and
manually staged Traefik syntax. It does not confirm applications or
observability are deployed:

```bash
kubectl kustomize clusters/belacca-production >/tmp/native-staging.yaml
```

## Research basis

The old production configuration follows the current Prometheus documentation
for `scrape_configs`, `rule_files`, recording/alerting rule groups, and
per-scrape sample limits:

- <https://prometheus.io/docs/prometheus/latest/configuration/configuration/>
- <https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/>
- <https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/>
- <https://prometheus.io/docs/practices/histograms/>
- <https://fluxcd.io/flux/monitoring/metrics/>

The image version/digest was resolved from the official Prometheus registry
metadata during implementation. Re-resolve it deliberately during upgrades;
do not replace it with a mutable `latest` tag. The checked-in JSON contracts
are validated as JSON and the Prometheus config/rules are validated with the
official `promtool` in coordinator/CI environments where that binary is
available.
