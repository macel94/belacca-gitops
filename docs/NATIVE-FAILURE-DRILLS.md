# Native production failure drills

This is the GitOps-side contract for issue [#10](https://github.com/macel94/belacca-gitops/issues/10).
It defines the checks, timing, evidence, and safety boundary for native production;
it does **not** grant permission to mutate the cluster. Host/node mutation is
owned by the [belacca-infrastructure](https://github.com/macel94/belacca-infrastructure)
repository and must be performed by an approved operator during a change window.

The current execution ledger is
[`NATIVE-DRILL-EVIDENCE.json`](NATIVE-DRILL-EVIDENCE.json). It intentionally
contains three `not_executed` records: this repository has no production
credentials, kubeconfig, SSH access, Cloudflare token, or operator approval, so
no timings or user-facing results are invented here. A record may be changed
only from an approved live execution report with sanitized evidence links.

## Objective and measurement boundary

- Recovery objective: **P95 strictly under 360 seconds** across at least three
  comparable approved measurements.
- The timer starts at `fault_injection_confirmed_at`: the UTC timestamp at which
  the approved fault injection is confirmed or the actionable failure alert is
  confirmed, whichever is the agreed start for that scenario.
- The timer stops at `recovery_verified_at`, only after every required check in
  this document passes. Node `Ready` alone is not recovery.
- `recovery_seconds` is the UTC elapsed time between those timestamps. Do not
  use a local wall-clock duration copied from a shell prompt.
- P95 uses the nearest-rank method: sort completed durations and select the
  item at rank `ceil(0.95 * n)`. With exactly three measurements, P95 is the
  slowest measurement.
- Drill duration is **not** an availability observation. It must not be added
  to `belacca-status/history`, `status.json`, `slo.json`, an availability
  denominator, or an error budget. If the drill causes user impact, the
  external status runner may record that separately under its own policy.
- The public synthetic is a single mutating Pong journey, not a load generator.
  Run at most one explicitly approved journey before and one after the fault
  per drill, never in a loop or on a schedule for this exercise.

## Required approvals, owners, and abort policy

The Incident Commander or Operations Lead must record an approval/change ID,
operator, independent observer, UTC window, scenario, target, rollback owner,
and evidence destination before the mutation gate. Each evidence record must
retain those fields; `pending` is not an approval.

| Drill | Target and owner | Fault and required result | Abort threshold | Rollback / recovery owner |
|---|---|---|---|---|
| Public edge | One approved native edge address (`.41` or `.42`); platform owner changes DNS, infrastructure operator is observer | Public-edge failover drill: withdraw exactly one failed edge A record using the manual DNS fallback, then verify the surviving edge serves all required checks. This is a traffic-withdrawal drill, not proof of host failure. | Abort before DNS mutation if baseline fails or record identity is ambiguous; restore the record and stop if the surviving edge/API fails, DNS does not converge, or the 360-second objective cannot be met | Platform owner restores the exact A record after verification; infrastructure operator owns any subsequent host recovery |
| Control plane/server | `belacca-k3s-01` / `.73`; infrastructure operator | One approved control-plane/server isolation or graceful reboot; surviving pinned API remains ready and etcd-backed | Abort if the pinned surviving API or etcd readiness fails, a second server is NotReady, or the target does not recover within the approved timeout | Infrastructure operator follows `belacca-infrastructure/docs/NATIVE-FAILURE-DRILL.md`; do not recreate the cluster or change GitOps |
| Longhorn replica/node degradation | One approved Longhorn node, normally the other edge/storage node; infrastructure operator mutates, platform owner verifies | One-node degradation/reboot with three-replica placement observed before and after; every protected volume returns healthy with the configured replica count and capacity headroom | Abort if any volume is degraded/faulted/unknown, a required survivor replica is lost, capacity falls below the pre-approved floor, a second node fails, or the timeout expires | Infrastructure operator restores the node and waits for Longhorn convergence; never change replica protection, delete a PVC, or repair a live SQLite file |

A combined edge/storage reboot may exercise both failure domains, but it must be
recorded as **one** scenario and one measurement. It must not be counted twice.
The current infrastructure procedure's scenario names and pinned API endpoints
are authoritative; do not invent a different kubeconfig or mutate this
repository to run a drill.

## Preflight and coordination

1. Open an approved change/incident record and designate the Incident Commander,
   mutation operator, observer, rollback owner, and evidence owner.
2. Confirm the current `belacca-infrastructure` drill procedure and status. Its
   guarded entrypoint is `scripts/native-failure-drill.sh`; the default `plan`
   operation is read-only. Resolve any recorded `.73` host-identity or
   Longhorn InstanceManager PDB blocker before requesting `run` for a storage or
   control-plane scenario. The public-edge slot uses the exact-record DNS
   withdrawal fallback and does not request a node reboot.
3. Confirm native context `belacca-native`, the scenario's pinned surviving API,
   all three Kubernetes servers Ready, Flux Kustomizations Ready, Traefik
   healthy on the surviving public edge(s), and Longhorn nodes/disks/volumes/
   engines/replicas healthy with sufficient survivor capacity.
4. Confirm no active incident, pending rollout, stale/unknown protected backup,
   degraded external monitoring, or unrelated maintenance is in progress.
5. Capture a sanitized baseline. It may include HTTP status, pass/fail, and
   elapsed seconds, but never response bodies, cookies, tokens, player names,
   room IDs, client addresses, or raw private telemetry.
6. Confirm the DNS record IDs and the known-good three-address inventory before
   an edge drill. DNS is Cloudflare DNS-only round-robin and is not health
   aware; the fallback is manual.
7. Run one scenario at a time. Wait for Longhorn rebuild/convergence and close
   the evidence record before starting another scenario.

The following infrastructure procedure is the mutation authority and is kept in
the other repository:

- [Approved native drill procedure](https://github.com/macel94/belacca-infrastructure/blob/main/docs/NATIVE-FAILURE-DRILL.md)
- [Current sanitized infrastructure status](https://github.com/macel94/belacca-infrastructure/blob/main/docs/NATIVE-FAILURE-DRILL-STATUS.md)
- [Guarded drill entrypoint](https://github.com/macel94/belacca-infrastructure/blob/main/scripts/native-failure-drill.sh)

This branch must not copy credentials, kubeconfigs, host inventory, or a second
mutation script. The infrastructure procedure's `edge-storage-02` and
`edge-storage-03` scenarios intentionally combine public-edge and Longhorn-node
failure. Record one such reboot as one combined scenario; do not use it to claim
both a separate edge-only measurement and a separate storage-only measurement.
The public-edge measurement in this ledger is the DNS-withdrawal failover path.
If host-level edge-only coverage is required later, obtain an
infrastructure-repository change first.

## Verification gate and stop condition

The observer records the first timestamp at which all of the following pass
again. A transient single check is not recovery; repeat the check according to
the approved timeout and record failures without private payloads.

### User-facing health

From outside the cluster, check the public canonical routes and, where useful,
use pinned `--resolve` checks against each surviving edge:

- `francesco.belacca.com/health` returns HTTP 200 and the expected health
  contract.
- `pong.belacca.com/health` returns HTTP 200.
- `stats.belacca.com/status` returns HTTP 200.
- The canonical portfolio aliases retain their permanent redirect contract.
- The public edge serving the check is identified by the probe method, not
  inferred from DNS round-robin.

### Pong API and two-player journey

Use the approved one-shot Pong synthetic from
`cloudnativepong/scripts/synthetic-check.mjs` with an explicitly supplied
`SYNTHETIC_BASE_URL=https://pong.belacca.com`. It must verify homepage, health,
room list, room create, room join, two unique WebSocket-compatible players,
playing state, and cleanup. The run must finish before the recovery timestamp;
if it creates a room after recovery verification, the timer is not valid.
Store only aggregate pass/fail and duration. Never copy the generated room name,
room ID, player assignment, response body, token, or client address into this
repository or the issue.

### Flux and Kubernetes state

Using the pinned surviving API and native context, verify:

- all expected nodes are Ready and schedulable after the planned recovery;
- `/readyz?verbose` is successful and includes the etcd check;
- all relevant pods are Ready, with no unexplained pending/terminating workload;
- `flux get sources git -A` and `flux get kustomizations -A` show the expected
  Ready state and current revisions; and
- the target edge's Traefik pod is Ready where the scenario requires it.

A Flux reconciliation command is not a failure injection and is not a reason to
force reconciliation repeatedly. Do not apply, patch, delete, or hand-edit a
GitOps resource as part of this drill.

### Longhorn storage state

Record sanitized status for Longhorn nodes, disks, volumes, engines, and
replicas. Recovery requires all of the following:

- every Longhorn node and disk required by the contract is Ready;
- every observed protected volume is `healthy`, not degraded/faulted/unknown;
- every volume has its configured three running replicas on distinct native
  nodes, including the expected survivor placement;
- rebuild/rebalance has converged and the approved survivor free-capacity floor
  remains satisfied; and
- `pong-api-data`, `goatcounter-data`, and Dex state remain single-writer and
  untouched. Do not mount any SQLite PVC into a second writer.

Do not delete protected PVCs, alter reclaim policy, disable Longhorn node-drain
protection, change replica count/settings, recreate the cluster, use `kubectl
exec` against a live SQLite writer, or copy a backup into a live database path.

## Manual DNS removal fallback

Because application DNS is direct round-robin, an unhealthy edge may continue
to receive traffic until its A record is removed. The platform owner may use
this fallback only under the approved incident/change record; it is not part of
the timer unless the scenario approval explicitly says so.

1. Using a protected shell and an out-of-band Cloudflare token, look up the
   exact A-record IDs for the affected hostname. Do not put the token in Git,
   shell history, a command argument, or evidence.
2. Remove only the failed edge's A record by its exact record ID. Preserve the
   other native edge addresses and the TTL/proxied policy. Do not use a broad
   hostname, wildcard, or bulk-delete operation.
3. Verify public DNS through at least two independent resolvers and verify the
   surviving edge directly with TLS hostname validation and the health checks
   above. Record the sanitized record ID, target address, UTC action, and
   operator; never record the token or full API payload.
4. Restore the removed A record from the approved inventory after the edge is
   healthy and the rollback owner authorizes restoration. Re-verify all three
   addresses and the canonical routes.

If a provider/API operation is unavailable, the fallback is an explicit manual
Cloudflare console change by the approved owner—not an invented API result. Do
not alter `k3s-api.belacca.com` as part of an application-edge withdrawal. A DNS
withdrawal must be timed from confirmed record mutation; it must not be mixed
with a host reboot timer.

## Evidence, P95, and postmortem

For each of the three records in `NATIVE-DRILL-EVIDENCE.json`, attach:

- approval/change or incident reference and operator/observer roles;
- scenario, target, pinned API endpoint, and infrastructure report reference;
- `fault_injection_confirmed_at`, `recovery_verified_at`, and computed
  `recovery_seconds`;
- sanitized baseline/recovery results for health, Pong CRUD/two-player/cleanup,
  Flux, and Longhorn;
- any DNS fallback action and restoration reference; and
- durable HTTPS evidence links from approved GitHub/status locations.

The validator calculates P95 only from completed records. A P95 miss (360
seconds or greater), failed required verification, unexpected user impact,
data-risk event, or monitoring gap requires a postmortem with corrective owner,
due date, and a follow-up measurement plan. Link that postmortem from the issue
and the affected evidence records. Do not mark an unexecuted or partial record
as passed.

The current ledger reports `p95_status: not_available` and
`comparable_measurements: 0`; this is an explicit validation limitation, not a
claim that the objective passed. The exact operator follow-up is to obtain
approval, clear the infrastructure blockers, run the three scenarios one at a
time, attach sanitized evidence, run `scripts/validate_native_drills.py`, and
update the issue with the resulting evidence/postmortem links.
