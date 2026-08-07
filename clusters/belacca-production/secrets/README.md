# Native cluster secrets

Native staging currently contains namespace declarations only. It does not
reconcile old-production OAuth, Cloudflare, analytics-admin, or other runtime
credential manifests. Those values must not be copied into native staging
before a separately reviewed native application and Secret lifecycle exists.

The native Flux root still decrypts its out-of-band `flux-system/sops-age`
Secret, whose private key is backed up through the private infrastructure
repository's `FLUX_AGE_PRIVATE_KEY` GitHub secret. No age private key or
plaintext Secret value belongs in this directory.

The `.sops.yaml` recipient is retained for future native Secret publication.
Do not apply encrypted manifests with kubectl; Flux kustomize-controller owns
any future decryption and reconciliation.
