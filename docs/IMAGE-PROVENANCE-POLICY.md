# Native production image provenance policy

Status: **enforced at Kubernetes admission for native application namespaces**.
The enforcement point is a fail-closed Kyverno validating admission webhook,
installed by Flux from `clusters/belacca-production/policy-system/` and gated by
the `native-image-policy` Flux Kustomization. This is compatible with native
k3s and does not depend on a separate deployment controller.

## Contract

A Pod entering native production (`pong`, `portfolio`, or `analytics`) must use
an image reference containing a complete `@sha256:<64 hex characters>` digest.
A tag alone, including `latest`, `sha-*`, or a semver tag, is not an immutable
production reference. Kyverno does not mutate tags (`mutateDigest: false`), so
an operator cannot accidentally turn a mutable promotion into an approved one.

First-party images are limited to these repository prefixes:

| Workload | Registry prefix | Required GitHub workflow identity |
| --- | --- | --- |
| Pong API, room, static, gateway | `ghcr.io/macel94/cloudnativepong-` | `https://github.com/macel94/cloudnativepong/.github/workflows/publish-images.yml@refs/heads/main` |
| Portfolio | `ghcr.io/macel94/francesco-belacca-site` | `https://github.com/macel94/francesco-belacca-site/.github/workflows/test-and-publish.yml@refs/heads/main` |

For each first-party image digest, Kyverno requires all three signed Sigstore
bundle attestations from the matching GitHub Actions keyless identity:

1. SLSA provenance (`https://slsa.dev/provenance/v1`), with the GitHub workflow
   build type;
2. CycloneDX SBOM (`https://cyclonedx.org/bom`); and
3. a vulnerability decision (`https://belacca.com/attestations/vulnerability/v1`)
   whose `policy` is `native-production-v1`, whose `maxSeverity` is `NONE`,
   `LOW`, or `MEDIUM`, and whose `knownUnfixed` is `false`.

The issuer is `https://token.actions.githubusercontent.com` and transparency
verification uses `https://rekor.sigstore.dev`. A missing, invalid, expired, or
identity-mismatched attestation blocks admission. The policy is not report-only.

The signed registry SBOM and signed vulnerability decision are separate
requirements: a registry SBOM alone is evidence, not an admission authorization.
A Trivy report with `exit-code: 0` is also not an authorization. Publishers must
make the vulnerability decision explicit and sign it for the exact image digest.

The machine-readable copy of this contract is
[`policy/image-policy.json`](../policy/image-policy.json), and the policy
manifests are under [`clusters/belacca-production/policies/`](../clusters/belacca-production/policies/).

## Vulnerability treatment

- Any fixed `HIGH` or `CRITICAL` finding blocks production.
- Any known-unfixed finding blocks production, regardless of severity.
- `NONE`, `LOW`, and `MEDIUM` findings may be promoted only when the signed
  decision attestation records the result and its exact image digest.
- A scanner outage, missing report, unsupported scanner result, or ambiguous
  severity is treated as failure to produce the required attestation and blocks
  promotion. `ignore-unfixed` is not an admission bypass.
- The publisher owns the SBOM and scan evidence. This GitOps repository owns the
  admission policy and never fabricates registry or live-cluster evidence.

The portfolio application publisher now builds the registry SBOM, scans the
pushed image digest, emits the signed `native-production-v1` vulnerability
decision, and records the exact image digest in its deployment Kustomization.
The workflow still fails closed before Git promotion when the decision exceeds
MEDIUM or contains known-unfixed findings. Operators should verify the resulting
digest and all three attestations with `cosign verify-attestation` or the
corresponding GitHub attestation tooling before relying on the rollout.

## Vendor and disposable images

Disposable CI images (`*:latest`, `*:test`, `*:supply-chain`, and locally built
images) are permitted only in isolated CI/k3d test overlays. They are never a
native Flux source or production contract. Native production must use an
approved vendor image/chart contract for third-party platform components;
version and digest changes remain reviewed GitOps changes. The first-party
workflow identity policy does not treat a vendor image as a Belacca-built image.

Kyverno's own bootstrap namespace is excluded by the Kyverno chart, and the
Flux controller bootstrap remains a platform trust boundary. Any future
platform-image hardening must pin those generated controller images by digest
before removing that boundary. This is a deliberate compatibility boundary,
not evidence that vendor artifacts have Belacca GitHub workflow provenance.

## Exceptions

There are no active exceptions (`active: []` in `policy/image-policy.json`). An
exception, if ever required, must be a reviewed Git change containing all of:

- **owner:** an accountable person or team;
- **rationale:** the finding, business need, and compensating control;
- **scope:** exact namespace, workload, image repository, and immutable digest;
- **expires:** an RFC 3339 UTC timestamp no later than 30 days after approval;
- a linked issue/review and a replacement or remediation plan.

Exceptions may not allow a mutable tag, remove digest verification, or waive
provenance identity for a broad repository prefix. They are expired by deleting
or updating the exception before the timestamp; an expired exception must never
be renewed implicitly. The policy owner reviews active exceptions weekly and
records closure/remediation in the linked issue.

## Validation and operator follow-up

Offline checks:

```bash
python3 scripts/validate-image-policy.py
bash scripts/validate-image-policy.test.sh
kubectl kustomize clusters/belacca-production >/tmp/native-production.yaml
```

The negative test feeds a mutable first-party `:latest` image to the validator
and requires rejection. This worktree has no production kubeconfig, registry
credentials, or live Kyverno endpoint, so it cannot claim a live admission
attempt. Before rollout, an operator must reconcile `native-policy-system`,
confirm Kyverno admission and webhook health, reconcile `native-image-policy`,
and submit a disposable invalid Pod in a non-production test namespace plus a
first-party digest whose three attestations have been verified. Record only
redacted admission/status output. Do not disable the webhook to recover a
failed promotion; fix the publisher attestations or revert the GitOps change.
