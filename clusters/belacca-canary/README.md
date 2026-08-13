# Disposable canary target

This directory contains the cluster-level safety foundation for the issue #6
canary. It intentionally does **not** contain application workloads, Flux
sources, production routes, credentials, or PVCs. A reviewed application
overlay may be added only when it uses the exact image digests and ephemeral
state required by `docs/RELEASE-GATES.md`.

Apply/reconcile this target only in an explicitly disposable cluster that
supports `admissionregistration.k8s.io/v1` `ValidatingAdmissionPolicy`. The
policy uses `failurePolicy: Fail`; if the API server cannot enforce it, the
target is not safe and promotion must stop.

The checked-in controls are:

- restricted Pod Security labels;
- zero Secret/PVC ResourceQuota;
- default-deny NetworkPolicy with DNS-only committed egress; and
- admission denial of Secrets, PVCs, Pod Secret/PVC references, and service
  account token mounts.

NetworkPolicy and admission enforcement must be verified in the actual cluster
before a release uses this target. No native-production Flux Kustomization or
native-production namespace is a dependency.
