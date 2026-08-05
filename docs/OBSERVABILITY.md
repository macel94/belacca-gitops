# Staged observability contract

## Current implementation

The cluster tree contains an opt-in, private Prometheus collector under
`clusters/vmi3474918/observability/`.

- Prometheus `v3.13.2` is pinned by the verified multi-architecture image digest.
- It is a plain Deployment, not a Prometheus Operator installation.
- It has no public Ingress, NodePort, or LoadBalancer.
- It stores at most seven days and 2 GB in an `emptyDir` volume.
- It runs one replica because this is a single-host demonstration layer, not a
  highly available monitoring service.
- It scrapes the Pong API and Flux controller metrics through explicit static
  service targets.
- It has no Kubernetes Secret access and no application labels containing room
  IDs, player names, IP addresses, or request contents.
- The Prometheus API is allowed only from the private Headlamp namespace by the
  checked-in policy. Use a private port-forward after runtime validation.

The Flux `observability` Kustomization has `prune: false` intentionally. This is
an opt-in/staged component: validate resource usage and CNI connectivity before
considering a future ownership/pruning change. The existing root `prune: false`
and protected PVC behavior are unchanged.

`synthetic-contracts.json` is the machine-readable external-check contract for
portfolio, Pong, analytics, and authenticated dashboard journeys. It contains
no credentials or collected results. `dashboard.json` is a private dashboard
query/panel definition; it is source material, not proof that Grafana is
installed or that the queries currently have data.

This repository does **not** currently install Grafana, Prometheus Operator,
blackbox-exporter, OpenTelemetry Collector, or a public metrics route. Those
are separate follow-up changes requiring CRD/chart/runtime validation. The
public site status page remains externally published and unknown by default;
Prometheus is not treated as its own external status authority.

## Scrape contract

The application contract is:

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
- `pong_websockets_active`
- `pong_sqlite_*`
- `pong_room_*`
- `pong_websocket_*`
- `pong_admission_*`

Do not add room ID, player name, client address, URL, or arbitrary error text as
metric labels. Use aggregate counters or bounded log/evidence fields instead.
The current sample limit for the Pong scrape is 100.

Flux controllers expose metrics on their existing internal HTTP service port;
the collector uses a sample limit of 500 for that target group. A missing Flux
metric series is a diagnostic gap, not proof that reconciliation is healthy.

## Rules and dashboards

`prometheus.rules.yml` contains proposed recording rules for:

- Pong request/error rates
- active rooms and WebSockets
- Flux Ready-condition failures
- fast and slow candidate burn-rate alerts

The rules are warning/diagnostic only until an external SLI source, owner, alert
destination, and measured SLO are approved. The candidate alerts must not be
represented publicly as achieved availability.

Useful initial dashboard panels, whether queried through a future private
Grafana or Prometheus itself, are:

```promql
sum(rate(pong_http_requests_total[5m]))
sum(rate(pong_http_requests_failure_total[5m]))
pong_rooms_active
pong_rooms_waiting
pong_rooms_playing
pong_websockets_active
sum(rate(pong_websocket_proxy_dial_failure_total[5m]))
sum(rate(gotk_reconcile_condition{status="False",type="Ready"}[5m]))
```

If a future dashboard is installed, keep it private through Headlamp/port-forward
or an identity-aware route. Do not expose Prometheus or Grafana directly on a
public hostname.

## Runtime validation checklist

Before treating this as deployed observability:

```bash
kubectl config use-context k3d-pong
kubectl kustomize clusters/vmi3474918/observability >/tmp/observability.yaml
kubectl apply --dry-run=server -f /tmp/observability.yaml
flux reconcile kustomization observability -n flux-system --with-source
kubectl -n observability get deploy,pod,svc,networkpolicy
kubectl -n observability port-forward service/prometheus 9090:9090
curl -fsS http://127.0.0.1:9090/-/ready
```

Then verify from Prometheus's target page that the Pong and Flux jobs are
healthy, and use a non-destructive connectivity check to confirm the
observability → Pong allow rule. Do not widen policies to `0.0.0.0/0` as a
shortcut. If resource pressure or CNI incompatibility appears, suspend the
`observability` Kustomization and revert this staged component through GitOps;
do not delete application PVCs or the cluster.

## Research basis

The configuration follows the current Prometheus documentation for
`scrape_configs`, `rule_files`, recording/alerting rule groups, and per-scrape
sample limits:

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
