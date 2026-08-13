# Native production encrypted backup and restore runbook

This runbook implements issue #5 for **native production** only. It never
creates a bucket, KMS key, credential, or plaintext Secret. Those are approved
and provisioned out of band. The checked-in jobs remain fail-closed until the
external operator has populated the named Secret interfaces and deliberately
sets both runtime gates to `true`.

## Scope and safety boundary

Protected SQLite sources are:

| Service | Namespace/workload | PVC | database path | writer schedule (UTC) |
|---|---|---|---|---|
| Pong | `pong/pong-api` | `pong-api-data` | `/source/pong.db` | 02:17 |
| GoatCounter | `analytics/goatcounter` | `goatcounter-data` | `/source/db.sqlite3` | 02:29 |
| Dex | `dex/dex` | `dex-data` | `/source/dex.db` | 02:41 |

Each writer remains one replica and each backup Pod mounts its PVC read-only.
The procedure must still obtain an approved quiesced/consistent source copy:
stop or fence the single writer according to the service-specific maintenance
procedure before enabling the gate. A read-only mount alone is not proof that a
live SQLite file was safe to copy.

Restore verification has no production PVC mount. It downloads to an ephemeral,
private target, validates the manifest, SHA-256, and `PRAGMA integrity_check`,
then deletes the temporary plaintext file when the Pod exits. It never writes a
native PVC and never uses `kubectl cp` against production.

## External prerequisites (must be tested, not asserted)

Provision out of band:

- an approved TLS-only, private S3-compatible bucket with anonymous access
  denied, versioning enabled, and provider WORM/object-lock protection for the
  retention window;
- customer-managed KMS/SSE-KMS encryption, with a key policy that separates
  backup writes, restore reads/decrypt, and key administration;
- a **writer identity** restricted to `ListBucket` on its exact prefix and
  `PutObject`/`AbortMultipartUpload` on that prefix. It must not have
  `GetObject`, `DeleteObject`, bucket administration, or access to other
  prefixes;
- a separate **restore identity** restricted to `ListBucket` on the exact
  prefix and `GetObject` on that prefix plus KMS decrypt. It must not have
  `PutObject` or `DeleteObject`;
- lifecycle rules retaining at least 35 distinct verified UTC daily backups and
  12 distinct verified UTC monthly backups. Lifecycle must not be the only
  copy policy and must not delete a currently required WORM-locked object.

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

- `NativeBackupStale` and `NativeBackupUploadOrVerificationMissing` for missed
  schedules, failed uploads, missing Secrets, or failed restore verification;
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

This worktree cannot access the approved object store, KMS, native cluster, or
production credentials, so it must not fabricate permission, retention,
upload, or full-service restore evidence. The exact operator follow-up is to
provision/test the external prerequisites above, populate the Secrets out of
band, run one verified upload/download and all three isolated application
rehearsals, and commit only redacted evidence if the evidence repository's
policy permits it.
