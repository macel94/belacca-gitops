# Native production notifications

Native Flux notification resources are maintained in
`clusters/belacca-production/notifications.yaml`. The destination Secret is
intentionally provisioned out of band as the `platform-notification-webhook`
Secret, and no endpoint or credential is stored in Git.

The contract separates diagnostic/ticket events from future page-worthy SLO,
routing, storage, and recovery notifications. Ownership, independent failure
domain, deduplication, grouping, inhibition, recovery, rotation, and incident
handoff are documented here and validated without contacting a receiver.

There is no paging claim until an approved destination is provisioned, tested,
and its failure/recovery path is observable. The native notification validator
must pass before reconciliation.
