# Historical reference tree

This directory is the retired `k3d-pong` / `vmi3474918` GitOps tree. It is
preserved for audit, migration history, and recovery-contract reference only.

- It is **not** native production.
- It is **not** a Flux deployment target.
- It must not be applied, reconciled, or used as a production rollback target.
- Normal workspace and CI validation must render
  `clusters/belacca-production/` instead.

Use the explicit `make manifests-historical` or
`python3 scripts/validate-observability.py --historical` audit commands when
this retired material must be inspected. Those commands do not confer
permission to deploy it.
