# Native cluster secrets

Secret values are encrypted with SOPS/age and are decrypted only by Flux in
`belacca-native`. Plaintext values are never committed. The age private key is
stored in the native `flux-system/sops-age` Secret and backed up through the
private infrastructure repository's `FLUX_AGE_PRIVATE_KEY` GitHub secret.

Only the encrypted manifests belong here. Do not apply them with kubectl; Flux
kustomize-controller owns their decryption and reconciliation.
