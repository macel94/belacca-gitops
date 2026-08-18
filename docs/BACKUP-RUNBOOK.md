# Native production encrypted backup and restore runbook

This runbook implements the native-production portion of issue #13. It never
creates a bucket, KMS key, credential, or plaintext Secret. The approved AWS S3
destination, identities, SSE-KMS settings, and monthly spend guard were
provisioned out of band on 2026-08-14; sanitized evidence is recorded in
[`docs/evidence/aws-native-backup-20260814.json`](evidence/aws-native-backup-20260814.json).
The checked-in jobs use externally managed runtime Secrets. Automation is enabled only after the approved source-consistency procedure, immutable provenance, and provider acceptance checks are complete.

## Scope and safety boundary

Protected SQLite sources are:

| Service | Namespace/workload | PVC | database path | writer schedule (UTC) |
|---|---|---|---|---|
| Pong | `pong/pong-api` | `pong-api-data` | `/source/pong.db` | 02:17 |
| GoatCounter | `analytics/goatcounter` | `goatcounter-data` | `/source/db.sqlite3` | 02:29 |
| Dex | `dex/dex` | `dex-data` | `/source/dex.db` | 02:41 |

Each writer remains one replica and each backup Pod mounts its PVC read-only. Backup Pods use filesystem group `1000` for Pong/GoatCounter and `1001` for Dex, matching the protected database file groups. Because these are Longhorn `ReadWriteOnce` volumes, every source backup Job requires pod affinity to the node hosting its corresponding single-writer workload; this prevents a backup from waiting indefinitely for a cross-node attach.
The procedure must still obtain an approved quiesced/consistent source copy:
stop or fence the single writer according to the service-specific maintenance
procedure before enabling the gate. A read-only mount alone is not proof that a
live SQLite file was safe to copy. The runner uses a 120-second bounded SQLite
lock/storage wait and retries a failed copy once using a fresh destination; it
then fails the Job with a diagnostic instead of waiting for the 30-minute Job
deadline.

Restore verification has no production PVC mount. It downloads to an ephemeral,
private target, validates the manifest, SHA-256, and `PRAGMA integrity_check`,
then deletes the temporary plaintext file when the Pod exits. It never writes a
native PVC and never uses `kubectl cp` against production.

## Provisioned provider state and remaining gates

Provisioned and tested out of band:

- Amazon S3 Standard in `eu-central-1`, private with anonymous access denied,
  versioning enabled, and S3 Object Lock `COMPLIANCE` mode with a 400-day
  default retention period;
- SSE-KMS with the AWS-managed S3 key and S3 Bucket Keys. A customer-managed
  CMK is intentionally deferred to avoid the fixed monthly cost described in
  issue #13;
- three service-scoped writer identities and one separate restore identity;
- account-wide AWS Budgets monthly cost guard of USD 8, chosen conservatively
  below the requested EUR 10 target with exchange-rate headroom, with actual and forecast notifications at
  50%, 80%, and 100% as applicable. Budgets is an alerting control, not a hard
  stop, and billing data can lag;

Operational evidence tracked after enabling production automation:

- the approved quiesced/consistent source procedure for Pong, GoatCounter, and
  Dex, including source revision and image digest evidence;
- verified production upload/download and isolated restore verification; the
  synthetic acceptance fixtures contain no production data;
- at least 35 verified daily and 12 verified monthly production retention
  points, plus a tested operator notification destination.

The provisioned bucket uses:

- a TLS-only, private S3 endpoint with anonymous access denied, versioning, and
  provider WORM/Object Lock protection for the retention window;
- separate writer and restore identities; routine identities have no delete or
  bucket-administration permission;
- lifecycle retention configured for current and noncurrent versions after the
  400-day compliance window plus a seven-day incomplete-multipart cleanup;

The writer identities are restricted to their own service prefixes; the restore
identity can list/read the backup prefix but cannot write or delete. Lifecycle
rules retain at least 35 distinct verified UTC daily backups and 12 distinct
verified UTC monthly backups. Lifecycle must not be the only copy policy and
must not delete a currently required WORM-locked object.

The Kubernetes Secret names/keys are runtime interfaces only. Populate them in
`pong`, `analytics`, `dex`, and `backup-system` as appropriate through the
private secret manager. Do not commit or print values:

- `<service>-backup-object-store`: `endpoint`, `bucket`, `prefix`, `region`,
  `access-key-id`, `secret-access-key` (writer identity);
- `<service>-backup-encryption`: `kms-key-id`, `encryption-context` (writer);
- `<service>-backup-runtime`: `automation-enabled`,
  `consistency-acknowledged`, `source-revision`, `image-digests` (writer);
- `backup-restore-object-store` in `backup-system`: the same six connection
  keys, but the restore identity;
- `backup-restore-runtime` in `backup-system`: `automation-enabled` and
  `consistency-acknowledged`, both `true` only after the external gate review.

The supplied job manifests reference these Secrets but intentionally do not
create them. An absent Secret or a gate other than exactly `true` produces a
failed Job and a visible alert condition rather than a false success.

Finished backup and restore-verification Jobs set
`failedJobsHistoryLimit: 0` and a 15-minute `ttlSecondsAfterFinished` safety
net. The CronJob controller may prune a failed Job sooner, while the TTL
controller independently cascades deletion to any finished Job and its Pod;
together these prevent stale failed Pods from accumulating. The cleanup does
not make a failed run successful and does not remove the immutable backup
artifact or its alert signal.

## Permission and encryption acceptance test

From a protected operator environment, with values supplied by the secret
manager and never placed in shell history, use the provider CLI/SDK equivalent
of these requests (the placeholders are not values to commit):

```text
writer:  PutObject s3://<bucket>/<prefix>/permission-test/<uuid> body=test, SSE-KMS=<approved-key>
writer:  ListBucket prefix=<prefix>/permission-test/<uuid>
writer:  GetObject same-key                         => MUST be AccessDenied
writer:  DeleteObject same-key                      => MUST be AccessDenied
restore: GetObject same-key                         => MUST succeed
restore: ListBucket prefix=<prefix>/permission-test/<uuid> => MUST succeed
restore: PutObject same-key                         => MUST be AccessDenied
restore: DeleteObject same-key                      => MUST be AccessDenied
both:    Get/List/Put/Delete prefix=<unrelated-prefix> => MUST be AccessDenied
```

1. Run the writer `PutObject` test using a disposable key under its exact prefix.
2. Confirm the writer receives `AccessDenied` for `GetObject`,
   `DeleteObject`, a different prefix, and bucket policy changes.
3. Confirm the object has provider-reported SSE-KMS with the approved customer
   key and the expected encryption context; capture only non-secret evidence.
4. Run a restore `GetObject`/`ListBucket` test for the disposable object.
5. Confirm the restore identity receives `AccessDenied` for `PutObject`,
   `DeleteObject`, unrelated prefixes, and bucket policy changes.
6. Delete the disposable test object only through an approved administrator
   path; never grant delete to either routine identity.
7. Verify versioning, WORM/object-lock mode/expiry, TLS certificate validation,
   lifecycle rules, and the counts of verified daily/monthly artifacts.

Do not mark these tests complete based on IAM policy text alone. Record the
provider, bucket alias, policy revision, KMS key alias (not key material), UTC
test times, and allow/deny results in protected incident evidence.

## Running and verifying automation

After the acceptance test and an approved quiesced-copy window:

```bash
kubectl config use-context belacca-native
kubectl -n flux-system get kustomization native-backup
kubectl -n pong get cronjob pong-backup
kubectl -n analytics get cronjob goatcounter-backup
kubectl -n dex get cronjob dex-backup
kubectl -n backup-system get cronjob,pod,service backup-metrics
```

Trigger one writer and one verifier at a time with explicit names, never by
scaling a production StatefulSet or mounting a second writer. Inspect the Job
JSON/log output for the machine-readable fields `key`, `sha256` or
`artifact_sha256`, `source_revision`, `integrity`, `started_at`,
`finished_at`, and `duration_seconds`. Redact endpoints, key IDs where policy
requires, and all credentials.

The Prometheus diagnostic endpoint is private. Expected alerts are:

- `NativeBackupConfigurationUnknown` when the external restore Secret or
  runtime gates are not ready. The Secret interfaces are externally managed;
  when both gates are true, the metrics endpoint reports readiness and backup
  success series become eligible for evaluation;
- `NativeBackupStale` and `NativeBackupUploadOrVerificationMissing` after the
  configuration becomes ready, for missed schedules, failed uploads, or failed
  restore verification;
- `NativeBackupIntegrityFailed` for a bad artifact/manifest/hash;
- `NativeBackupDailyRetentionLow` below 35 distinct verified UTC days;
- `NativeBackupMonthlyRetentionLow` below 12 distinct verified UTC months.

The alert destination is still an out-of-band operator responsibility. The
repository's Flux notification contract does not claim paging until that
receiver is provisioned and tested.

## Restore rehearsal for all services

For each `pong`, `goatcounter`, and `dex`:

1. Select the newest verified artifact from the restore identity.
2. Record its object key, SHA-256, source revision, image digests, manifest
   integrity result, download start/finish, and isolated verification timing.
3. Run the corresponding `restore-verify` CronJob. It uses an ephemeral target
   only and removes plaintext data on exit.
4. For a full application rehearsal, deploy the service's pinned image and
   configuration into a newly named disposable namespace/cluster with a new
   PVC. Never use `belacca-native`, a native node IP, or a live production PVC.
5. Verify the service-specific health check and schema/application startup.
6. Preserve only redacted machine-readable evidence; destroy the isolated
   target with its exact generated name after review.

For Pong, the existing application checkout's
`cloudnativepong/scripts/restore-rehearsal.sh` remains the supported full
application rehearsal. It requires an explicitly acknowledged `pong-restore-*`
cluster and a downloaded verified copy; it refuses native production and `pong`.
GoatCounter and Dex full application rehearsals require their owning application
images/configuration in an isolated target; the checked-in verifier proves the
artifact restore but cannot claim a production application rehearsal without
those external images and credentials.

## RPO/RTO measurement

The intended target is a 24-hour maximum backup age (RPO target) and 4-hour
service recovery (RTO target), subject to the nightly schedules and external
storage availability. Measure actuals per rehearsal:

```yaml
service: <pong|goatcounter|dex>
artifact_sha256: <64 lowercase hex>
source_revision: <redacted revision or immutable digest>
integrity: ok
isolated_target: true
backup_started_at: <UTC RFC3339>
backup_finished_at: <UTC RFC3339>
download_started_at: <UTC RFC3339>
restore_finished_at: <UTC RFC3339>
rpo_seconds: <incident time minus artifact created_at>
rto_seconds: <restore start to service health success>
production_pvc_written: false
single_writer_preserved: true
operator: <approved operator identifier>
notes: <no player names, tokens, request logs, or credentials>
```

The provider and live cluster are now reachable through the approved operator
path, and the synthetic upload/download and permission matrix are recorded in
sanitized evidence. The remaining operator follow-up is to approve the
quiesced-copy procedure, set the runtime gates only during that window, run one
verified production upload/download and all three isolated application
rehearsals, build the daily/monthly retention history, and test the notification
destination. Commit only redacted evidence; never commit credentials, bucket
identifiers treated as sensitive, plaintext databases, or recovery keys.
