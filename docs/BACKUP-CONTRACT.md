# Native production Pong backup and restore contract

This is a contract for a future operator-managed backup service for **native
production**. Pong, GoatCounter, and Dex state has already been quiesced,
integrity-checked, and restored into native Longhorn-backed RWO PVCs. External
object storage and scheduled backups remain unprovisioned. The former `k3d-pong` runtime and its local volumes are retired historical
sources, not recovery targets. No bucket, CSI snapshot, CronJob, access
credential, encryption key, or external storage endpoint is created by this
repository. The checked-in helper does not upload backups or contact object
storage.

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

## Native production object-storage contract (not provisioned)

An approved S3-compatible object store is an external prerequisite for native
production. The operator must provision the bucket, TLS endpoint, access
policy, and lifecycle policy out of band. GitOps must not create a bucket,
guess a provider, upload a backup, or put credentials in this repository.

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

## Native production encryption contract (not provisioned)

- TLS protects the upload and download path.
- Objects are encrypted at rest with the provider's approved KMS/SSE mechanism;
  the key is customer-managed where the selected provider supports it.
- The key policy separates routine backup writes from restore reads and key
  administration. Key rotation and revocation are operator responsibilities.
- Restore access must decrypt only into a disposable target. Plaintext database
  files must use protected local storage and be removed after the rehearsal.
- A successful `integrity_check` is not proof that encryption, retention, or
  object immutability is configured.

## Native production Secret-name and key contract (names only; no values in Git)

These are runtime interfaces, not Secret manifests. The names are stable so a
future native production operator-run Job or external backup agent can consume
them without changing application code. Secret values, URLs, bucket names, key
IDs, and credentials must be supplied by a protected secret manager or private
operator procedure.

| Namespace | Secret name | Required keys | Purpose |
|---|---|---|---|
| `pong` | `pong-backup-object-store` | `endpoint`, `bucket`, `prefix`, `region`, `access-key-id`, `secret-access-key` | S3-compatible endpoint and native production write identity; values are external |
| `pong` | `pong-backup-encryption` | `kms-key-id`, `encryption-context` | Approved KMS/SSE configuration; values are external |
| `pong` | `pong-backup-restore-object-store` | `endpoint`, `bucket`, `prefix`, `region`, `access-key-id`, `secret-access-key` | Separate least-privilege read identity for native production restore verification |

Do not create empty placeholder Secrets: an empty Secret looks provisioned but
cannot establish a native production backup guarantee. Before any automated job
is introduced, validate that the external values exist, the endpoint is
approved, the bucket policy and KMS policy are tested, and the operator can
retrieve the values without exposing them in shell history, CI logs, Git, or
incident tickets.

## Native production automation gate and acceptance test

No CronJob is committed for native production until all of the following are true:

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

Until these prerequisites are met, the supported native production procedure is
manual: copy the quiesced database to protected local storage, run
`backup-restore.sh backup` and `verify`, and run the isolated rehearsal. This
establishes neither off-host retention nor an automated RPO.

## Native production recovery and emergency rules

- A failed rehearsal is rolled back by allowing the script to delete only its
  own `pong-restore-*` cluster, or by running the printed exact cleanup command.
- A failed native production application rollout is rolled back through the
  application image/tag commit and native Flux reconciliation; do not restore
  the live PVC in place.
- Never run `k3d cluster delete pong`, `k3d cluster delete k3d-pong`,
  `kubectl delete pvc pong-api-data`, or a live `kubectl cp` into
  `/data/pong.db` as native production recovery.
- If an artifact fails integrity verification, quarantine it and use a different
  verified artifact. Do not “repair” it in a live production PVC.
- Do not use a live native `.41`/`.42` workload as a restore target; use an
  isolated copied-artifact rehearsal and retain the single-writer contract.
