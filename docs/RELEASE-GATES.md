# Progressive delivery and rollback gates

This document is the operator contract for issue #6. It defines a disposable
canary boundary without claiming that production infrastructure or credentials
were exercised from this repository.

## Delivery stages

The reviewed release descriptor is `releases/release-policy.json`:

1. **test** — deploy the candidate to an isolated test target and run the
   portfolio health/homepage checks plus the canonical Pong user journey.
2. **canary** — deploy the same candidate digests to the disposable
   `belacca-canary` target. It is not a second production owner and has no
   production hostname, production Secret, native-production PVC, or route to
   native production. Run the same checks again.
3. **full** — after a reviewed Git change, promote the exact candidate digests
   to the native-production application repositories/Flux paths. Run the same
   checks after reconciliation.

Readiness is necessary but not sufficient. A Flux Ready condition or
Deployment rollout does not promote a release when a user-facing check fails.

## Candidate requirements

Every image supplied to `scripts/run-release-gates.py` is recorded as an
exact `repository@sha256:<64 lowercase hex>` identity in `imageReferences` and
as a matching entry in `imageDigests`. A tag such as `sha-<commit>` is useful provenance metadata but is not a
promotion reference; the application workflow records the tag together with the
exact digest, and native production reconciles the digest-pinned reference. The release must also include:

- source commit SHAs for every application repository;
- the Flux revision/Kustomization revision that reconciled the target;
- a successful, exact-digest provenance/attestation verification result for
  every image (the evidence `verifiedImages` set must equal `imageDigests`); and
- durable links to check output and attestation evidence.

The registry and attestation service are external prerequisites. This clean
worktree cannot authenticate to GHCR or perform a production Flux
reconciliation, so no digest, attestation, rollout result, or production
outcome is asserted here. The gate fails closed when any of those values is
missing.

A recommended verification shape is:

```text
cosign verify-attestation \
  --type slsaprovenance \
  --certificate-identity=<approved-build-workflow-identity> \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  <repository>@<exact-sha256-digest>
```

Store the resulting bundle/log in the approved immutable evidence location;
do not commit credentials, tokens, full response bodies, room IDs, player
names, or client addresses.

## Canary safety boundary

`clusters/belacca-canary/` is a policy-only target foundation. Before adding an
application overlay, the overlay must be reviewed against these controls:

- namespace label `belacca.com/release-stage=canary` and restricted Pod
  Security labels;
- `ResourceQuota` limits Secrets and PVCs to zero;
- `ValidatingAdmissionPolicy` uses `failurePolicy: Fail` and denies Secrets,
  PVCs, Pod secret/PVC references, and service-account token mounts;
- default-deny ingress and egress, with DNS as the only committed egress;
- no `Ingress`, `LoadBalancer`, production `Service`, production namespace,
  production Secret, production PVC, or native-production Flux Kustomization;
- disposable application data must use `emptyDir` or an application-supported
  in-memory/test backend, never a copied or mounted native PVC; and
- teardown is a reviewed operator action after evidence is retained.

NetworkPolicy rendering is not proof that the cluster CNI enforces it. The
operator must verify the admission policies and non-destructive connectivity
from the actual canary cluster before relying on this target.

## Running the gates

Use a pinned checkout of the Pong repository and its canonical synthetic
runner. The command mutates a disposable Pong room and therefore must never be
pointed at native production unless the full production check is explicitly
being run for the full stage:

```bash
python3 scripts/run-release-gates.py \
  --release-id <release-id> \
  --stage canary \
  --portfolio-url https://<disposable-portfolio-host> \
  --pong-url https://<disposable-pong-host> \
  --pong-command node /workspace/cloudnativepong/scripts/synthetic-check.mjs \
  --source cloudnativepong=<40-char-sha> \
  --source francesco-belacca-site=<40-char-sha> \
  --image ghcr.io/macel94/cloudnativepong-api=sha256:<64-hex> \
  --image ghcr.io/macel94/cloudnativepong-room=sha256:<64-hex> \
  --image ghcr.io/macel94/cloudnativepong-static=sha256:<64-hex> \
  --image ghcr.io/macel94/cloudnativepong-gateway=sha256:<64-hex> \
  --image ghcr.io/macel94/francesco-belacca-site=sha256:<64-hex> \
  --flux-revision <flux-revision> \
  --source-committed-at <RFC3339-UTC> \
  --provenance-evidence <immutable-attestation-evidence-uri> \
  --evidence-uri <immutable-run-evidence-uri> \
  --readiness-passed \
  --provenance-verified \
  --output evidence/<release-id>.json
```

The runner exits non-zero for a failed user journey after writing `blocked`
evidence. A missing readiness/provenance flag exits before any check. It never
prints or stores response bodies.

The portfolio check is `/health` with body `ok` and the homepage must return
HTTP 200. The Pong command must be the upstream canonical journey, which
covers homepage/health, room list/create/join, two unique WebSocket-compatible
players entering `playing`, and cleanup.

## Deliberate failed-canary rehearsal

This is a safe, bounded rehearsal against a disposable target. It is not a
production test and must be run only after the canary target is provisioned:

1. Deploy a candidate that intentionally makes the canary portfolio `/health`
   return a non-200 response, or point the gate at a disposable black-hole
   endpoint. Do not alter the native-production Flux path.
2. Reconcile only the canary/test Kustomization and capture its Flux revision,
   readiness result, exact image digests, and verified provenance.
3. Run the gate command above. It must write `outcome: "blocked"`, exit 1, and
   include all three check results.
4. Revert the canary candidate through a reviewed Git change (or forward-fix
   it), reconcile only the canary target, and rerun the gates.
5. Retain both JSON results and the Git/Flux reconciliation links. The failed
   canary's bounded impact is the absence of a production route/state change;
   no native-production rollback is required.
6. For a failed full stage, create a reviewed revert/forward-fix in the owning
   application/GitOps repository, wait for Flux reconciliation, rerun the
   checks, and add `rollbackCompletedAt` to the evidence. Never roll back by
   hand-editing a live Pod or restoring a production PVC.

This repository has not executed that rehearsal because it lacks a canary
cluster, registry credentials, external synthetic endpoints, and production
Flux access. The exact follow-up is to provision the disposable target with
these manifests, verify admission/CNI behavior, run the rehearsal, and attach
the real evidence artifact to the release change.

## Evidence and DORA metrics

Each release artifact links source SHAs, exact image digests, provenance for
all exact image digests, Flux revision, readiness, all user-facing checks,
timestamps, and outcome. Run `scripts/calculate-dora-metrics.py` over the
reviewed artifacts to calculate the four release metrics reproducibly:

| Metric | Calculation | Required fields |
| --- | --- | --- |
| Release lead time | `productionStartedAt - sourceCommittedAt` | source and production timestamps |
| Deployment frequency | successful `full` releases per UTC day/reporting window | stage and promoted outcome |
| Change failure rate | full releases requiring rollback / full releases | full outcome and rollback fields |
| Recovery time | `rollbackCompletedAt - failureDetectedAt` | failure and rollback timestamps |

Do not count blocked canaries as full deployments or hide them as successful
promotions. The evidence validator rejects incomplete or contradictory
artifacts.

## Rollback command path

Rollback is a reviewed Git change, not a `kubectl rollout undo` shortcut:

```bash
git revert <candidate-promotion-commit>
git push origin <reviewed-rollback-branch>
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization <affected-kustomization> -n flux-system
flux get kustomizations -n flux-system
```

Use the actual owning application/GitOps repository and Kustomization name;
never guess a target or reconcile any tree other than native production.
Record the resulting commit and Flux revision in the release evidence. Do not
delete or overwrite `pong-api-data`, `goatcounter-data`, Dex state, or any
native production PVC during rollback.
