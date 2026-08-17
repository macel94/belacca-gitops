# Native production game-day drills (issue #4)

This is the **native-production** runbook for `belacca-native`, the three-server
k3s cluster declared in `clusters/belacca-production/`. It replaces the
retired-runtime document; the historical document is preserved in
[`GAME-DAY-DRILLS-HISTORICAL.md`](GAME-DAY-DRILLS-HISTORICAL.md) and must not be
executed.

## Safety contract

- **Production actions were not executed from this worktree.** No credential,
  cluster access, external synthetic runner, DNS provider, hypervisor, or
  Longhorn UI access is available here. The evidence record therefore reports
  `not-executed-production-access-unavailable`; it does not invent timings or
  customer impact.
- The only supported context is exactly `belacca-native`. The helper and every
  command below must stop before a mutation if the current context differs.
- The protected native PVCs are `pong/pong-api-data`,
  `analytics/goatcounter-data`, and `dex/dex-data`. Never delete, recreate,
  detach, resize, overwrite, or mount any of them into a second writer.
  `observability/prometheus-native-data` is retained diagnostic state and is also
  outside these drills.
- The only mutable workload actions in this runbook are deletion of one
  explicitly named ready Pod (Traefik or Pong API) and reversible node
  scheduling maintenance. No selector-based deletion, namespace deletion,
  PVC command, direct Pod edit, or root-prune change is allowed.
- `scripts/native-game-day.py` is the safety gate. Its default is read-only
  preflight/dry-run. A real mutation additionally requires `--execute`,
  `--ack-issue 4`, `--confirm-production`, and the exact native context. It
  never performs DNS, hypervisor, Git push, or Longhorn API-provider actions.
- Capture command output only after removing tokens, Secret data, player names,
  room IDs, request bodies, client addresses, and private host telemetry.

## Common preflight and evidence

The operator and incident lead must be named before the maintenance window.
Run the read-only preflight from an approved operator workstation:

```bash
python3 scripts/native-game-day.py preflight \
  --evidence /tmp/native-game-day-preflight.json
```

The preflight checks the exact context, three named server nodes, etcd/API
readiness, native Traefik DaemonSet/pods, Flux source/Kustomization readiness,
Pong API/Service/PVC, Longhorn nodes/volumes, and the external probe contract.
It does not apply, delete, cordon, drain, patch, reconcile, or print Secret
values. Review the generated file before starting a drill.

For every drill, record these timestamps in UTC (RFC 3339 with `Z`):

1. **Detection** — first external/internal signal and its source;
2. **Acknowledgement** — incident lead and time accepted;
3. **Mitigation start/end** — exact action and command result;
4. **Recovery** — first passing internal checks and first passing external
   synthetic journey;
5. **User impact** — affected host/journey, start/end, failed probe count, and
   HTTP/connection symptoms only (no payloads or identifiers).

Use [`native-game-day-evidence.json`](native-game-day-evidence.json) as the
sanitized record shape. A `null` field means it was not measured; it must not
be replaced with an estimate. Attach only redacted command output and review
it with the platform owner before publishing.

## Drill 1 — one public edge unavailable

**Scope and expected impact:** one named native Traefik Pod on one named edge
node, one Pod only. A short connection failure or TLS retry is possible while
that host-network Traefik process is replaced; the other two direct DNS edges
must continue serving. Do not remove a DNS A record as the fault injection.

**Preconditions:** preflight passes; all three edge nodes are Ready; the target
Traefik Pod is Ready and its node is one of
`belacca-k3s-01`, `belacca-k3s-02`, `belacca-k3s-03`; at least two other Traefik
Pods are Ready; no active certificate renewal or platform incident; external
Pong and portfolio journeys pass.

**Abort criteria:** context is not `belacca-native`; target is not an exact
Traefik Pod name in `kube-system`; fewer than two other Ready edge Pods; any
protected PVC appears in the target or command; API/etcd quorum is unhealthy;
or an unrelated user-impacting incident starts.

**Execute:**

```bash
python3 scripts/native-game-day.py restart-traefik-pod \
  --pod <exact-ready-traefik-pod-name> \
  --node <exact-edge-node-name> \
  --execute --ack-issue 4 --confirm-production
```

The helper verifies the name, node, labels, readiness, and peer count before
issuing one exact Pod deletion. It does not delete the DaemonSet or Service.

**Detection and recovery verification:** record the first synthetic failure (if
any), Traefik replacement Ready time, `kubectl -n kube-system rollout status
daemonset/traefik`, Ingress/service endpoints, and successful portfolio/Pong
external journeys through all pinned edge IPs. Confirm no unexpected Flux,
certificate, or API errors.

**Rollback:** no Git rollback is needed. If the replacement does not become
Ready, stop further drills, inspect the named Pod/events/logs, and follow the
Traefik HelmRelease rollback through GitOps. Never hand-edit the DaemonSet or
remove the native DNS record without the separate DNS change procedure.

## Drill 2 — one control-plane/server unavailable

**Scope and expected impact:** exactly one named native k3s server,
`belacca-k3s-01`, `belacca-k3s-02`, or `belacca-k3s-03`, made unavailable by the
approved infrastructure owner. This is a control-plane/failure-domain drill,
not a `kubectl delete node` drill. The remaining two embedded-etcd members must
retain quorum and the API must remain usable; workloads may lose the selected
edge and Longhorn replica placement during recovery.

**Preconditions:** preflight passes; the incident lead has an approved
hypervisor/host maintenance window and an out-of-band console; all three
servers are Ready; `etcdctl endpoint status`/the k3s-supported equivalent shows
three healthy members and quorum; no Longhorn rebuild, cert renewal, or other
node maintenance is running; external synthetics pass; the operator has
confirmed the selected server is not the only current holder of a required
single-writer application Pod.

**Abort criteria:** no out-of-band power/console authorization; any uncertainty
about the selected node identity; less than three healthy etcd members before
start; API or remaining-node readiness fails before injection; a second server
or quorum member becomes unhealthy; or a protected PVC would be moved or
mounted by a second writer. Do not proceed with a second node outage.

**Execute:** this repository deliberately cannot power off a production host.
The approved operator must use the infrastructure provider's exact host
operation for the selected node and record only the node name, timestamps, and
provider operation ID. Do **not** run `kubectl delete node` as the injection.

**Detection and recovery verification:** record provider/etcd detection,
acknowledgement, API request success from the remaining nodes, embedded-etcd
member health/quorum, Flux controller health, all three Traefik desired/ready
counts, Longhorn replica health, and external portfolio/Pong journeys. Recovery
is the node returning to Ready, etcd membership healthy, Longhorn rebuilding
complete, and synthetics passing; do not call it recovered merely because
`kubectl` responds.

**Rollback:** restore power/connectivity through the provider using the exact
node operation. Do not remove the member from etcd, reset k3s, delete the Node
object, or force-rejoin it as an incident shortcut. If quorum is lost, abort
all other drills and use the k3s/etcd incident procedure.

## Drill 3 — Pong API restart with SQLite PVC preserved

**Scope and expected impact:** one explicitly named `pong-api` Pod in namespace
`pong`; the Deployment and `pong/pong-api-data` claim remain untouched. Existing
lobby requests may see a brief retry/failure; the SQLite file must remain on the
same protected RWO claim and the one-writer contract must remain true.

**Preconditions:** preflight passes; exactly one API Pod is Ready and owned by
the native Pong Deployment; its volume claim is exactly `pong-api-data`; a
verified, quiesced backup artifact exists according to `BACKUP-CONTRACT.md`;
no active room-impacting incident; external Pong journey passes.

**Abort criteria:** target is not the exact ready API Pod; target has more than
one writer or does not mount exactly `pong-api-data`; the PVC is absent,
Pending, not Bound, or has unexpected ownership/reclaim metadata; backup
precondition is not independently verified; or any command contains a PVC
mutation/copy/restore operation.

**Execute:**

```bash
python3 scripts/native-game-day.py restart-pong-api-pod \
  --pod <exact-ready-pong-api-pod-name> \
  --execute --ack-issue 4 --confirm-production
```

The helper checks the pod's claim and one-writer invariant, then deletes only
the exact Pod. It never deletes or patches the PVC and never copies data into
`/data/pong.db`.

**Detection and recovery verification:** record API probe failure/retry,
replacement Pod Ready time, Deployment availability, claim identity and
volume attachment, `/health`, `/api/rooms`, and a normal two-player
WebSocket-compatible synthetic journey. Record whether any pre-existing room
was interrupted without recording room identifiers.

**Rollback:** a Pod restart has no Git rollback. For a bad application image,
revert the immutable image/tag commit in `cloudnativepong`, then reconcile the
native `pong` Kustomization. For suspected SQLite corruption, stop, preserve
the PVC, quarantine the artifact, and use the isolated restore rehearsal; never
restore over the live claim.

## Drill 4 — Longhorn replica/node degradation

**Scope and expected impact:** one named Longhorn node or one named replica of
one non-critical test volume, selected by the storage owner. Production
application volumes are observed, not detached or overwritten. A replica may
be rebuilding and the selected test workload may have elevated latency; no
protected SQLite PVC may be used as the fault-injection target.

**Preconditions:** preflight passes; the storage owner has identified a
non-production/disposable Longhorn test volume or an approved node-maintenance
window; all protected volumes (`pong-api-data`, `goatcounter-data`, `dex-data`,
and `observability-prometheus-data`) have healthy replicas; three nodes and
Longhorn managers/engine image processes are healthy; rebuild capacity and
free space are recorded; external synthetics pass.

**Abort criteria:** no disposable test volume or storage-owner approval; the
selected volume is protected or serves SQLite; replica count would fall below
the Longhorn policy; another rebuild/degraded volume exists; free space,
manager, engine, or API health is already degraded; or a second node is needed.

**Execute:** this repository does not patch Longhorn CRDs or invoke a provider
failure. The storage owner uses the approved Longhorn node-maintenance or
provider-console operation for the exact node/replica, with scheduling and
replica eviction settings recorded before and after. Never use a broad
`kubectl delete` against Longhorn resources and never detach a production PVC
as a test.

**Detection and recovery verification:** record Longhorn volume/replica state,
engine attachment, rebuild start/end, node conditions, free space, and any
synthetic user impact. Verify all protected volumes remain healthy and attached
to one writer, and verify Pong/portfolio external journeys before ending the
drill.

**Rollback:** cancel the exact maintenance operation or restore the exact node
scheduling/replica setting through the Longhorn owner procedure. Wait for
rebuild health; do not delete replicas or volumes to hide a degraded state.

## Drill 5 — failed application reconciliation and Git rollback

**Scope and expected impact:** one reviewed Pong application revision and the
native `flux-system/pong` Kustomization only. The intentional failure must be
introduced in the owning application Git repository by a reviewed, reversible
change; this GitOps repository does not fabricate or apply a bad manifest.
Existing pods should continue serving while Flux reports the failed revision;
if an invalid revision is applied, the measured user impact and rollback must
be bounded by the Pong RTO.

**Preconditions:** preflight passes; application owner has a reviewed test
commit and rollback commit; the expected immutable image/digest and prior good
revision are recorded; Flux source and Kustomization are Ready; protected PVC
and root prune settings are unchanged; external synthetic journeys pass; the
notification destination limitation is acknowledged.

**Abort criteria:** failure would touch the native root, platform HelmRelease,
any protected PVC, prune setting, Secret, or unrelated Kustomization; rollback
commit is not available; source revision is ambiguous; Flux/API/quorum is
unhealthy before injection; or the failure cannot be bounded to `pong`.

**Execute:** the application owner pushes the reviewed failing revision, then
the operator uses only these scoped reconciles:

```bash
flux reconcile source git cloudnativepong -n flux-system
flux reconcile kustomization pong -n flux-system
```

Do not use `--with-source` on the native root for this drill and do not alter
live Pods by hand.

**Detection and recovery verification:** record source/Kustomization condition,
revision, event/notification signal, acknowledgement, external Pong failure
journeys, rollback commit time, reconcile time, Deployment readiness, and
successful external recovery. A missing notification Secret is recorded as a
coverage limitation, not as a successful page.

**Rollback:** revert the failing application commit in `cloudnativepong`, push
the reviewed revert, reconcile the source and only `pong`, and verify the
previous immutable image/digest and external journeys. If rollback fails, stop
and escalate; do not enable root pruning or delete application state.

## Drill 6 — external synthetic recovery verification

**Scope and expected impact:** external observation only. No production
mutation is performed by this drill. The status publisher checks all supported
native edges and the public portfolio/Pong/analytics journeys; authenticated
dashboard checks remain proposed until credentials and an approved runner are
provisioned.

**Preconditions:** status-repository owner has approved the run; runner is
outside the cluster and has no production write credentials; targets are the
native hosts in `SITES.md`; probe release, location, timeout, and redaction
policy are recorded; the drill incident ID is available.

**Abort criteria:** runner would run inside production, credentials would be
stored in Git/logs, probe would create real player/user data, authenticated
credentials are unavailable, or the runner cannot distinguish all three edge
addresses. A local curl is not an external SLO result.

**Execute:** trigger one approved status-repository run or wait for its
scheduled hourly observation. Record the sanitized observation IDs and per-
journey pass/fail results only. Do not commit raw probe output, cookies, room
names, tokens, or client addresses here.

**Detection and recovery verification:** correlate the first failing and first
passing external observations with internal recovery timestamps. For Pong,
require homepage, health, room API, two-player WebSocket-compatible journey,
and cleanup. For portfolio require homepage/health and alias redirects; for
analytics require `/status`, harmless `/count`, and `/count.js`. Record the
edge IP and probe location only where the external publisher's privacy policy
permits it.

**Rollback:** no production rollback. Stop the runner or disable only the
approved test schedule through its owner if it produces unsafe data; do not
change DNS or public routing to make a probe pass.

## Recovery policy comparison

The policy is 99% availability over 30 days, no SLA. A 30-day window has
`720` hourly slots; 99% permits at most `7.2` failed equivalent hourly slots
(operational reporting must use the status repository's documented rounding and
valid-slot rules). A controlled drill's recovery duration is a separate
measure and must not be added to availability arithmetic.

For each drill, calculate:

- `recovery_seconds = first_external_passing_observation - injection_start`;
- `user_impact_seconds = impact_end - impact_start`, with `null` if no impact;
- `failed_external_slots` and `valid_external_slots` from the external status
  publisher; and
- `rto_met = recovery_seconds <= 14400` for each catalogued service's 4-hour RTO.

Compare the observed result with the applicable service RTO in
`catalog/services.json` and the 99%/30d policy. The current catalog status is
`proposed/not measured`; this branch cannot promote it to achieved. The
separate aspirational controlled-drill P95-under-six-minutes objective is not
an acceptance result until enough reviewed runs exist.

## Evidence and review gate

Before publication, the incident lead and platform owner review
[`native-game-day-evidence.json`](native-game-day-evidence.json) for:

- exact scope and command/resource names;
- detection, acknowledgement, mitigation, recovery, and user impact;
- quorum/API, Traefik, Longhorn, Flux, application, and external results;
- secret/private-data redaction; and
- measured recovery compared with RTO and 99% policy.

The checked-in [`NATIVE-GAME-DAY-ISSUE-4-REVIEWED.md`](NATIVE-GAME-DAY-ISSUE-4-REVIEWED.md)
is a sanitized, reviewed evidence/postmortem record of the implementation
limitation, not a claim that production drills ran. Replace its explicit
follow-up fields only after the operators execute and review the drills.
