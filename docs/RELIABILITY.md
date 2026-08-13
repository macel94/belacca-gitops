# Native production reliability metadata and runbook index

This repository describes only native production: the three-server k3s cluster
reconciled from `clusters/belacca-production/` and identified by the
`belacca-native` context. The catalog is the machine-readable source for
service owners, hosts, tiers, dependencies, SLO intent, RTO, RPO, dashboards,
and runbooks.

Each public service has an internal 99%/30d objective with no SLA. External
status and SLO evidence are published from outside the cluster; native
Prometheus remains private diagnostic telemetry. A controlled recovery-drill
P95 under six minutes is a separate objective and requires three comparable
approved measurements before it can be claimed.

## Deployment boundary

- Native Flux owns `clusters/belacca-production/`.
- Public application and operator routes use the native edge and documented
  firewall boundary.
- State remains single-writer on protected Longhorn-backed RWO PVCs.
- Restore, capacity, and chaos rehearsals use isolated disposable targets.
- Production rollback is a reviewed Git change followed by Flux reconciliation.
