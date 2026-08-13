# Native production game-day drills

These drills target the maintained native production cluster only. Run one
approved scenario at a time from the `belacca-native` context. Verify the
cluster identity, node set, protected PVC names, Longhorn health, Flux state,
and abort thresholds before mutation.

## Required evidence

Record approval, owner, fault class, start and stop timestamps, user impact,
detection, acknowledgement, mitigation, rollback, health/API checks, Pong
journey checks where applicable, cleanup, storage state, and a follow-up issue.
Missing or malformed evidence is unknown and cannot prove recovery.

## Scenarios

### Public-edge failure

Withdraw one approved native edge through the reviewed DNS/provider procedure.
Verify the remaining edges, public health, redirects, Pong API CRUD, and the
canonical two-player journey. Restore the edge and measure convergence.

### Control-plane/server failure

Cordon or isolate one approved native server only after quorum, capacity, and
Longhorn checks pass. Verify embedded-etcd quorum, API readiness, Traefik,
Flux, workloads, and recovery. Reconcile the node and confirm it is schedulable.

### Application restart

Restart the native Pong API through a reviewed GitOps change or bounded
workload action. Preserve `pong-api-data`, verify SQLite integrity and API CRUD,
and confirm the two-player journey and cleanup.

### Longhorn degradation

Use an approved replica/node degradation scenario without deleting protected
PVCs. Verify replica health, volume attachment, read/write state, application
availability, and recovery headroom.

### Failed reconciliation and rollback

Promote a deliberately invalid disposable application change through the
reviewed Git path. Verify that validation or readiness blocks it, revert the
change, reconcile native Flux, and attach detection/recovery evidence.

## Safety boundary

Never delete protected production PVCs, recreate native production, expose
internal ports, inject public load, or claim a six-minute P95 from fewer than
three comparable approved measurements. Failed or incomplete drills produce a
follow-up issue/postmortem rather than changing the objective.
