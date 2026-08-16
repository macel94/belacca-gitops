# Flux recovery record — 2026-08-13

## Scope

This record covers the native production cluster (`belacca-native`) and the
Flux-managed sources observed on 2026-08-13. It is an operational record, not
an availability or SLO claim. The backup destination was provisioned and tested
in a later operator change on 2026-08-14; the historical observations below
remain date-scoped.

## Observed state

Flux controllers and all three k3s nodes were running, but the following
resources remained unhealthy:

- `flux-system/pong`: failed dry-run because the application revision emitted
  `PrometheusRule/pong/pong-capacity` (`monitoring.coreos.com/v1`), while the
  native cluster intentionally runs standalone Prometheus and does not install
  Prometheus Operator CRDs.
- `flux-system/native-policies`: blocked by its dependency on `pong`.
- `flux-system/native-backup`: failed health checks because
  `backup-system/backup-metrics` could not create a Pod. The namespace quota
  correctly rejected the Deployment because its container had no CPU or memory
  requests or limits.
- `longhorn-system/longhorn`: upgrade retries were exhausted and Helm rolled
  back. Kyverno rejected Longhorn's generated pre-upgrade Job because its
  vendor image was tag-only.
- Flux notification events had historical dispatch failures from stale
  provider Secret references. The checked-in providers use the in-cluster
  Alertmanager address and do not require those Secrets; delivery still needs
  the operator-provisioned Alertmanager Telegram Secret and live matrix.

The intermittent Flux probe timeouts were secondary symptoms during the same
period. Controller Pods and nodes remained Running/Ready, and healthy child
reconciliations continued.

## Root causes and changes

1. **Pong monitoring API mismatch** — removed `capacity-alerts.yaml` from the
   native-staging Kustomization. The capacity alerts were not discarded: they
   were migrated into the native Prometheus file-based rules in
   `observability/config.yaml`, which is the monitoring implementation the
   cluster actually runs. The server overlay retains its Prometheus Operator
   resource for environments that install that CRD.
2. **Backup quota mismatch** — added bounded CPU requests and memory limits to
   all three restore-verification CronJobs and the backup metrics Deployment.
   This keeps the four-Pod quota meaningful while allowing the workload to be
   admitted.
3. **Backup external prerequisite boundary at the time of this record** — the
   restore Secret interfaces were intentionally absent from Git and the live
   cluster. The metrics server stayed Ready and exposed
   `belacca_backup_configuration_ready=0` with zero success/retention metrics,
   while scheduled writers and restore jobs remained fail-closed. Since then,
   the reliable immutable AWS backup destination and Secret interfaces have been
   provisioned and synthetic-tested; the runtime gates remain false, so this
   record still does not claim production backup success.
4. **Longhorn GitOps hook incompatibility** — set
   preUpgradeChecker.jobEnabled: false, the Longhorn chart's documented
   setting for Argo CD/GitOps installations. This avoids the generated
   tag-only pre-upgrade Job while retaining Longhorn manager and HelmRelease
   health checks.
5. **Pong image supply-chain gate** — the first attestation-enabled release
   exposed fixed base-image findings and the reviewed non-affected OpenPGP
   transitive-code finding. Pong now refreshes Alpine packages, updates
   `x/crypto`, records exact VEX scopes, and signs provenance, SBOM, and
   vulnerability decision attestations before recording deployment tags.
6. **Regression prevention** — extended the backup and observability validators
   to require resource budgets, the configuration-unknown metric, and the
   migrated Pong alert group.

## Validation and rollout

Before pushing:

```sh
kubectl kustomize clusters/belacca-production >/tmp/native-production.yaml
python3 scripts/validate-backup.py
python3 scripts/validate-observability.py
python3 scripts/validate-image-policy.py
python3 scripts/validate-notifications.py
```

After Flux observes the pushed revisions:

```sh
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
flux get kustomizations -A
flux get helmreleases -A
kubectl -n backup-system get deploy,pod
kubectl -n longhorn-system get helmrelease longhorn
kubectl -n flux-system get events --sort-by=.lastTimestamp
```

Recovery is complete only when `pong`, `native-policies`, `native-backup`, and
Longhorn are Ready, the backup metrics Pod is admitted and Ready, and no new
notification-controller Secret-reference errors appear. Alertmanager's
operator-managed Telegram Secret and delivery matrix are external prerequisites
and must not be fabricated in Git.
