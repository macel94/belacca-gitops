# Native production Flux notifications

This document records the current, intentionally incomplete notification
boundary for **native production** (`clusters/belacca-production/`). Native
production is the active platform. The former `k3d-pong` tree under
`clusters/vmi3474918/` is historical and is not a live notification target.

## Current state

The names-only platform-notification-webhook contract is committed in
[`../clusters/belacca-production/notifications.yaml`](../clusters/belacca-production/notifications.yaml)
and is wired into the native root Kustomization. It contains:

- `Provider/platform-webhook` in `flux-system`, using Flux's `generic`
  provider and referring only to the out-of-band Secret named
  `platform-notification-webhook`;
- `Alert/platform-errors` for error events from native Flux
  `GitRepository`, `Kustomization`, and `HelmRelease` resources; and
- `Alert/platform-deployments` for `info` events whose messages match the
  `succeeded` or `ready` inclusion patterns.

The source coverage is intentionally explicit. Both Alerts cover
GitRepositories and Kustomizations in `flux-system`, and HelmReleases in
`analytics`, `cert-manager`, `dex`, `flux-system`, `headlamp`, `kube-system`,
and `longhorn-system`. The event metadata identifies the cluster as
`belacca-native` and the environment as `native-production`.

The destination Secret is **intentionally absent**. No endpoint, token,
header, fake destination, Secret object, or Secret data is committed. No live
cluster mutation has been performed. The Provider is therefore a contract
only and is expected to remain unable to deliver events until its out-of-band
prerequisite exists. There is no paging claim, and no notification delivery
should be described as provisioned.

The labels and event metadata mark both Alerts as `diagnostic`, with
`page-policy: not-configured`. The deployment Alert is not a page route: its
success/ready events are diagnostic or ticket context only until a destination
owner separately approves and configures a notification policy.

This notification boundary does not change service objectives. Public services
target 99% availability over 30 days; this is a policy target, not an SLA.
Controlled-drill recovery P95 under six minutes is a separate recovery measure
and must not be inferred from notification delivery.

## Event classification and handling

| Flux event | GitOps classification now | Page status | Expected handling |
| --- | --- | --- | --- |
| `error` from a covered Flux source | reconciliation incident candidate | no page configured | create or update an operational ticket after review; escalate through the incident process if impact or persistence is confirmed |
| `info` matching `succeeded` or `ready` | deployment/reconciliation diagnostic | never a page in this contract | retain as deployment context or a low-urgency ticket when useful |
| any event from an uncovered kind or namespace | outside this contract | none | use the owning system's existing telemetry and runbook |

These classifications are policy labels, not a claim that an operator currently
receives the events. The missing Secret and destination mean delivery remains
unprovisioned.

Receivers should deduplicate repeated reconciliation events using a stable
identity such as:

```text
cluster + namespace + involved kind + involved name + severity + reason
```

The Flux revision, message, and timestamp should remain event details rather
than create unbounded groups. A new revision or a materially different reason
may start a new group; a recovery (`succeeded`/`ready`) should close or update
the corresponding error group instead of creating an unrelated incident.
Receiver owners must define retry, retention, rate-limit, and group windows
before treating these events as operational notifications. No receiver-side
policy is committed here.

## Harmless diagnostic verification

Verification is deliberately non-paging and read-only until an authorized
operator provisions the destination. A safe verification should:

1. confirm that the active cluster context is the native-production context;
2. inspect the Provider and both Alerts for their conditions and the expected
   Secret-reference error, without creating or applying a resource;
3. after an approved out-of-band destination exists, send or induce one
   harmless, non-paging diagnostic event in a controlled window;
4. confirm the receiver's deduplication, metadata, retention, and redaction;
   and
5. remove the diagnostic test record according to the receiver's retention
   policy, without retaining credentials or event payloads unnecessarily.

A missing `platform-notification-webhook` Secret is an expected visible
prerequisite, not a reason to add a fake Secret or endpoint to Git. Do not use a
production failure, a public route, or a paging test as notification
verification.

## Escalation and incident handoff

The platform owner reviews a covered `error` event for scope, duration, and
customer impact. If it is actionable, the reviewer opens or updates the
incident/ticket with the Flux object identity, reason, revision, first and
latest timestamps, affected service, and the applicable runbook. The handoff
must identify the current incident owner and the next escalation contact; it
must not rely on an unprovisioned webhook.

When public impact is confirmed, use the normal incident process and service
owner escalation. When reconciliation recovers, record the recovery and close
or downgrade the incident only after checking service health. Notification
signals do not replace probes, dashboards, or the separate controlled-drill
recovery measurement. Do not announce a page, an acknowledgement, or an SLA
response based solely on these manifests.

## Safe out-of-band provisioning and rotation placeholders

Provisioning and rotation are operator-owned follow-up work. They must happen
through the approved private secret manager or protected administrative path,
not through Git, issue comments, shell history, CI logs, or this document.
There is intentionally no real command here.

The out-of-band record to complete is:

```text
cluster context: <approved-native-production-context>
namespace: <flux-system>
Secret name: <platform-notification-webhook>
required key: address = <approved-HTTPS-notification-endpoint>
optional key: token = <operator-managed-token>
optional key: headers = <operator-managed-header-map>
owner: <approved-platform-or-receiver-owner>
retention: <approved-receiver-retention>
rotation schedule: <approved-rotation-schedule>
```

Before provisioning, the owner selects and approves the receiver, HTTPS
endpoint, authentication scheme, access controls, retention, and page-vs-ticket
policy. The Secret must contain only the receiver's documented keys. The
endpoint and authentication values remain outside Git. Provisioning is not
complete until the Secret exists in the native `flux-system` namespace and a
harmless diagnostic has been verified without paging.

For rotation, the owner prepares a replacement credential in the approved
secret manager, updates the same out-of-band Secret reference without changing
this manifest, verifies a harmless diagnostic, confirms the old credential is
revoked, and records the rotation date and owner outside Git. If the receiver
requires a header map, its values follow the same private handling rules.

A future change that enables paging requires a separate reviewed policy change
covering severity mapping, on-call ownership, escalation timing, deduplication,
maintenance suppression, and a harmless test. This contract alone does not
authorize paging.

## References

- [Flux Provider API](https://fluxcd.io/flux/components/notification/providers/)
- [Flux Alert API](https://fluxcd.io/flux/components/notification/alerts/)
