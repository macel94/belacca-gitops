# Native production Flux notifications and paging

This document is the operator contract for **native production**
(`clusters/belacca-production/`). Native production is the active platform; the
former `k3d-pong` tree under `clusters/vmi3474918/` is historical and is not a
live notification target.

## Status and ownership

The checked-in resources in
[`../clusters/belacca-production/notifications.yaml`](../clusters/belacca-production/notifications.yaml)
provide separate diagnostic and page lanes, plus a matching recovery lane:

- **Ticket/dashboard lane:** `Provider/platform-webhook` uses a generic HTTPS
  webhook and sends covered Flux errors plus successful/ready deployment
  context. It is diagnostic and never a page.
- **Page and recovery lane:** `Provider/platform-page-webhook` uses a generic
  HMAC webhook. `Alert/platform-page-errors` is narrowly scoped to the named
  root/application Kustomizations and the Traefik, Longhorn, and cert-manager
  HelmReleases. `Alert/platform-page-recovery` sends matching successful/ready
  events so the receiver can resolve or update the existing incident.

The approved destination is an **operator-owned PagerDuty-compatible incident
 gateway** in an independent failure domain managed outside native
production. It must not be hosted by
native k3s, Flux, native DNS, Traefik, Prometheus, or Longhorn. The platform
owner owns approval, access control, retention, receiver policy, and the
incident handoff. The on-call owner and next escalation contact are recorded in
the private operator incident record, not in this repository.

The destination is **not provisioned by this worktree**. No endpoint, token, or Secret value is committed; routing keys are also kept out of Git. The page destination contract is the
out-of-band Secret `flux-system/platform-page-notification-webhook`, with
`address` and `token` keys. The diagnostic destination contract remains
`flux-system/platform-notification-webhook`; its `address`, optional `token`,
and optional `headers` are also out of band. A missing Secret is an expected,
visible prerequisite and must not be replaced by a fake value.

The machine-readable policy is
[`../clusters/belacca-production/notification-routing.json`](../clusters/belacca-production/notification-routing.json).
The evidence file deliberately records
`not-performed-in-worktree`; it is not a claim of live delivery:
[`notification-verification-evidence.json`](notification-verification-evidence.json).

## Actionability policy

Flux readiness events alone are not a user-facing SLO alert. Page-worthy
signals require a high-level impact gate:

1. **SLO burn:** an approved external durable SLO source must assert both the
   short and long burn thresholds (14.4x for 5 minutes and 6x for 1 hour in the
   native Prometheus contract). The external status repository remains the
   public SLO source; native Prometheus currently has a fail-closed proposed
   zero placeholder, so it cannot claim an achieved SLO or create a page.
2. **Routing failure:** a routing failure must page only after an independent routing health gate
   confirms customer impact for 10 minutes. A single Traefik or low-level
   component error remains diagnostic.
3. **Storage failure:** page only after an independent storage health gate
   confirms customer impact for 10 minutes. A single Longhorn warning, PVC
   event, or replica problem does not page without the impact gate.
4. **Flux reconciliation:** page-lane Flux events are limited to named parent
   Kustomizations and platform HelmReleases. Individual low-level component
   failures go to the diagnostic lane unless a confirmed SLO, routing, storage,
   or parent-impact condition exists.

The public service policy remains 99% availability over 30 days, not an SLA.
The controlled-drill recovery P95 under six minutes is a separate recovery
measure and is not an alert threshold.

The native Prometheus rules expose the proposed SLO/routing/storage signals and
an observable `BelaccaNotificationPathNotProvisioned` warning. Notification failure is observable through Provider conditions, Kubernetes warning events, and the independent receiver monitor. The rules do not
silently convert missing metrics into pages. The notification controller's
Provider conditions, Kubernetes `NotificationDispatchFailed` warning events,
and redacted controller logs are the native failure signals. Because a failed
notification path cannot page through itself, the independent receiver owner
must monitor endpoint health and run periodic diagnostic delivery.

## Deduplication, grouping, inhibition, and recovery

The receiver must use this stable incident identity:

```text
cluster + environment + routingClass + namespace + kind + name + reason
```

Use a 10-minute grouping window. The Flux revision, message, and timestamp are
event details, not grouping identity; otherwise every reconciliation would make
another incident. A materially different reason or approved new revision may
start a new group.

The receiver policy is:

- repeated events with the same identity deduplicate;
- a parent service/page identity inhibits duplicate child component pages while
  the parent incident is active;
- deployment success/ready diagnostics never suppress or create pages;
- approved maintenance suppresses page delivery while diagnostics remain
  available; and
- `page-recovery` with the same identity resolves or updates the existing
  incident and never opens a second incident.

Recovery notifications are delivered through the page provider and are verified
against the original incident identity before closure.

The receiver owner must configure retry, retention, rate limiting, redaction,
and maintenance suppression before enabling the page lane. Flux itself does
not implement receiver-side deduplication or inhibition.

## Safe out-of-band provisioning and rotation

Provisioning is an operator-owned action through the approved private secret
manager or protected administrative path. Do not put values in Git, issue
comments, shell history, CI logs, or this document. The operator record must
capture, outside Git:

```text
cluster context: <approved-native-production-context>
namespace: flux-system
diagnostic Secret: platform-notification-webhook
page Secret: platform-page-notification-webhook
page receiver: <approved-independent-operator-owned-gateway>
page owner: <approved-platform-on-call-owner>
next escalation: <approved-escalation-contact>
retention: <approved-receiver-retention>
rotation schedule: <approved-rotation-schedule>
```

The receiver must accept HTTPS and verify Flux generic-HMAC `X-Signature` using
the page Secret's `token`. The page endpoint is supplied by the Secret's
`address`; no endpoint is present in the Provider manifest. Provisioning is not
complete until both Secret references have valid conditions and a harmless
non-paging diagnostic is verified.

For rotation, generate a replacement credential in the approved secret
manager, update the same out-of-band Secret, run the harmless diagnostic,
confirm the receiver accepted the replacement, revoke the old credential, and
record the date, owner, and result privately. Do not change the manifest or
copy the credential into this repository.

## Harmless diagnostic verification matrix

Live verification was not performed in this worktree: there is no native
cluster context, approved receiver, endpoint, routing key, or token here. Do
not fake a received event. An authorized operator must perform the following
in a controlled window, without a production outage or a paging test:

1. Confirm the active context is the approved native-production context and
   inspect Provider/Alert conditions without printing Secret data.
2. Verify the diagnostic Secret and page Secret exist with only the documented
   keys; redact all values.
3. Induce one harmless, reversible reconciliation event on a non-critical test
   object covered by the diagnostic lane. Do not inject a production failure or
   use a public route.
4. Verify one received diagnostic event has cluster/environment/object identity,
   redacted message data, and no credential or private payload leakage.
5. Deliver the same event repeatedly and verify deduplication and the 10-minute
   grouping window.
6. Verify a child event is inhibited while its parent page identity is active,
   and verify deployment info does not page.
7. Induce or observe the corresponding successful/ready event and verify the
   receiver resolves or updates the same incident identity; recovery must be
   delivered and must not create a new incident.
8. Temporarily exercise the receiver failure path in an approved test window
   and verify Provider conditions, `NotificationDispatchFailed`, redacted logs,
   and the independent receiver monitor. Restore the receiver and clean up the
   diagnostic record according to retention policy.

Record only redacted outcome metadata in
`docs/notification-verification-evidence.json`. Never commit event payloads,
URLs, tokens, routing keys, or screenshots containing secrets.

## Escalation and incident handoff

The platform owner reviews every page-lane event for scope, persistence, and
customer impact. The handoff record must contain:

- stable incident identity and Flux involved object;
- reason, first/latest timestamps, and source revision;
- affected public service and SLO/routing/storage impact evidence;
- the applicable runbook in `docs/RELIABILITY.md`;
- current incident owner and acknowledgement time; and
- the next escalation contact and escalation deadline.

The operator opens or updates the incident in the independent paging service,
then checks public probes, dashboards, Flux conditions, and service health.
Escalate to the platform owner immediately when the impact gate is confirmed;
escalate to the next contact at the privately approved deadline if the owner
has not acknowledged or impact persists. A recovered Flux event alone does not
close an incident: verify customer health first.

Notification signals do not replace external probes, dashboards, or the
controlled-drill recovery measure. Do not announce a page, acknowledgement,
recovery, or SLA response from the manifests alone.

## References

- [Flux Provider API](https://fluxcd.io/flux/components/notification/providers/)
- [Flux Alert API](https://fluxcd.io/flux/components/notification/alerts/)
- [Flux monitoring metrics](https://fluxcd.io/flux/monitoring/metrics/)
- [PagerDuty Events API v2](https://developer.pagerduty.com/api-reference/368ae3d938c9e-send-an-event-to-pager-duty)
