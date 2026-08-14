# Native production Pong backup and restore contract

This is the contract for the native-production encrypted backup implementation.
Pong, GoatCounter, and Dex state has already been quiesced, integrity-checked,
and restored into native Longhorn-backed RWO PVCs. This repository now provides
fail-closed scheduled writer and isolated restore-verification Jobs under
`clusters/belacca-production/backup/`, plus private freshness/integrity/
retention metrics and alerts. The approved AWS S3 destination, access identities,
SSE-KMS configuration, and monthly spend guard were provisioned out of band on
2026-08-14 and are recorded in sanitized
[`docs/evidence/aws-native-backup-20260814.json`](evidence/aws-native-backup-20260814.json).
Runtime Secret values remain external and are not created or committed here.
Native production is the only maintained source and recovery plane; rehearsals
use isolated copied artifacts. The runner cannot start until its out-of-band
automation and consistency gates are exactly `true`. The checked-in application
helper does not upload to object storage; only the reviewed native backup runner
performs an upload after those gates pass.

**Native production is the active restore target.** It uses
`clusters/belacca-production/`, Longhorn-backed RWO PVCs, and single-writer
SQLite workloads. Future restore rehearsals must use a copied artifact and an
isolated target; never overwrite a live native PVC.

## Native production protected source and target

| Item | Contract |
|---|---|
| Source workload | Native production `pong/pong-api` with one replica and `--db-path=/data/pong.db` |
| Source PVC | Native production `pong/pong-api-data`, `ReadWriteOnce`, Flux prune-disabled, never deleted for backup/recovery |
| Logical database | `/data/pong.db` in native production |
| Recovery target | A copied database in a newly created disposable `pong-restore-*` k3d cluster/PVC |
| Native production target | Never overwrite native production `pong-api-data` or `/data/pong.db` during a rehearsal |

A source copy must be made during an approved native production maintenance window
with the API stopped or otherwise quiesced. A byte-for-byte read of a mounted
live SQLite file is not a backup procedure. The existing helper uses SQLite's
online backup API after the operator has obtained a local copy and runs
`PRAGMA integrity_check` on the source, backup, and temporary restored database.

## Native production object-storage contract (provisioned out of band; automation gated)

The approved destination is Amazon S3 Standard in `eu-central-1`. The bucket,
Object Lock, versioning, lifecycle, access policy, identities, and TLS-only
endpoint were provisioned out of band. GitOps must not create a bucket, guess a
provider, upload a backup, or put credentials in this repository. The current
provider state is proven by sanitized synthetic acceptance evidence; this does
not yet claim that a live production backup has been completed.

Required provider behavior:

- TLS is required for API access; certificate verification must remain enabled.
- The bucket has versioning enabled and rejects anonymous access.
- Objects use a stable prefix such as `pong/<cluster-id>/sqlite/` selected by the
  operator; the real bucket, endpoint, and tenant are not specified here.
- Uploads are written as new, timestamped objects. A backup object is never
  overwritten in place.
- The object-store policy allows the backup writer to create/list its prefix and
  allows a separate restore identity to read it. Delete permission is withheld
  from the routine backup identity.
- The store provides a provider-supported immutability/WORM control for at least
  the retention window, or the operator records why that control is unavailable.
- The bucket lifecycle retains at least **35 daily verified backups** and at
  least **12 monthly verified backups**. Lifecycle deletion is not a recovery
  action and must not run during an incident without an approved exception.
- Each object is accompanied by metadata or a sidecar manifest containing the
  UTC creation time, source SHA-256, SQLite integrity result, native production
  source Git/Flux revision, deployed image digests, and operator/runbook
  reference. Do not put player names, tokens, or request logs in the artifact.

## Native production encryption contract (provisioned; administration external)

- TLS protects the upload and download path.
- Objects are encrypted at rest with SSE-KMS using the AWS-managed S3 key and S3
  Bucket Keys. A customer-managed key was deliberately not added initially to
  avoid the fixed monthly CMK cost identified in issue #13.
- The three writer identities can generate data keys only for their service
  prefixes; the separate restore identity can decrypt objects for verification.
  Human/provider administration remains separate. Key policy, rotation, and
  revocation are provider/operator responsibilities.
- Restore access must decrypt only into a disposable target. Plaintext database
  files must use protected local storage and be removed after the rehearsal.
- A successful `integrity_check` is not proof that encryption, retention, or
  object immutability is configured.

## Native production Secret-name and key contract (names only; no values in Git)

These are runtime interfaces, not Secret manifests. The names are stable so a
future native production operator-run Job or external backup agent can consume
them without changing application code. Secret values, URLs, bucket names, key
IDs, and credentials must be supplied by a protected secret manager or private
operator procedure. The canonical Pong names remain
`pong-backup-object-store`, `pong-backup-encryption`, and
`pong-backup-restore-object-store` for compatibility with existing operator
procedures; analytics and Dex use the corresponding `<service>-` names below.

| Namespace | Secret name | Required keys | Purpose |
|---|---|---|---|
| `pong`, `analytics`, `dex` | `<service>-backup-object-store` | `endpoint`, `bucket`, `prefix`, `region`, `access-key-id`, `secret-access-key` | S3-compatible endpoint and that service's native production write identity; values are external |
| `pong`, `analytics`, `dex` | `<service>-backup-encryption` | `kms-key-id`, `encryption-context` | Approved KMS/SSE configuration; values are external |
| `backup-system` | `backup-restore-object-store` | `endpoint`, `bucket`, `prefix`, `region`, `access-key-id`, `secret-access-key` | Separate least-privilege read identity for native production restore verification |
| `pong`, `analytics`, `dex` | `<service>-backup-runtime` | `automation-enabled`, `consistency-acknowledged`, `source-revision`, `image-digests` | External automation gate and evidence metadata; values are external |
| `backup-system` | `backup-restore-runtime` | `automation-enabled`, `consistency-acknowledged` | External restore verification gate; values are external |

Do not create empty placeholder Secrets: an empty Secret looks provisioned but
cannot establish a native production backup guarantee. The live Secret
interfaces are now populated out of band with the provisioned identities, but
all runtime gates remain `false`. Before enabling any automated job, validate
that the approved quiesced source procedure is available and retrieve values
without exposing them in shell history, CI logs, Git, or incident tickets.

## Native production automation gate and acceptance test

CronJobs are committed in a fail-closed state; they cannot upload or verify
anything until all of the following are true:

1. The object store and lifecycle/immutability policy are provisioned and
   independently reviewed.
2. The three Secret interfaces above are populated out of band and tested
   without printing values.
3. The backup identity cannot delete or read unrelated prefixes.
4. A verified upload and a verified download are performed in a disposable
   environment.
5. `cloudnativepong/scripts/restore-rehearsal.sh` passes using a downloaded
   copy, with all live production contexts absent from the operation.
6. Alerting for missed backup age, failed integrity checks, upload failures, and
   retention-policy drift has an acknowledged native production operator
destination.

Until the remaining gates and evidence are met, the supported native production
procedure is manual: copy the quiesced database to protected local storage, run
the application's `backup-restore.sh backup` and `verify`, and run the isolated
rehearsal. The checked-in scheduled Jobs remain visibly failed/disabled rather
than claiming an automated RPO. Use [`BACKUP-RUNBOOK.md`](BACKUP-RUNBOOK.md)
for exact Secret interfaces, permission tests, evidence fields, and the
GoatCounter/Dex full-application rehearsal limitation.

## Native production recovery and emergency rules

- A failed rehearsal is rolled back by allowing the script to delete only its
  own `pong-restore-*` cluster, or by running the printed exact cleanup command.
- A failed native production application rollout is rolled back through the
  application image/tag commit and native Flux reconciliation; do not restore
  the live PVC in place.
- Never delete an unrelated disposable target, run `kubectl delete pvc
  pong-api-data`, or use a live `kubectl cp` into `/data/pong.db` as native
  production recovery.
- If an artifact fails integrity verification, quarantine it and use a different
  verified artifact. Do not “repair” it in a live production PVC.
- Do not use a live native `.41`/`.42` workload as a restore target; use an
  isolated copied-artifact rehearsal and retain the single-writer contract.
