# Native production secrets

Native production contains reviewed namespace declarations and encrypted
runtime Secret interfaces owned by Flux. Plaintext OAuth, Cloudflare,
analytics-admin, and other credential values remain out of Git and are not
copied from the retired k3d runtime. Secret consumers and lifecycle changes
require a reviewed production GitOps change.

The native Flux root still decrypts its out-of-band `flux-system/sops-age`
Secret, whose private key is backed up through the private infrastructure
repository's `FLUX_AGE_PRIVATE_KEY` GitHub secret. No age private key or
plaintext Secret value belongs in this directory.

The `.sops.yaml` recipient is retained for future native Secret publication.
Do not apply encrypted manifests with kubectl; Flux kustomize-controller owns
any future decryption and reconciliation.
