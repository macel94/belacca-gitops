# Agent instructions: belacca-gitops

This repository is the cluster-level native-production source of truth. Read [`belacca-platform/docs/gitops-delivery.md`](https://github.com/macel94/belacca-platform/blob/main/docs/gitops-delivery.md) for the complete cross-repository delivery model.

## Ownership

Own Flux bootstrap, child `GitRepository`/Kustomization resources, native Kubernetes resources, routing, policies, and cluster-level documentation. Application source, Dockerfiles, and workflow-generated application image pins remain in the owning application repositories.

- Portfolio source: `macel94/francesco-belacca-site`, Flux path `./deploy`.
- Pong source: `macel94/cloudnativepong`, Flux path `./k8s/overlays/native-staging`.
- Native production context: `belacca-native`.

## Change and deployment workflow

1. Render/validate the affected Kustomizations and run repository tests.
2. Commit and push `main`.
3. Reconcile `flux-system` or the affected child Kustomization only after the remote commit exists: `flux reconcile source git flux-system -n flux-system`, then `flux reconcile kustomization flux-system -n flux-system`.
4. Verify source revision, applied Kustomization revision, workload image/digest, rollout health, and public behavior.

Do not manually edit a child application's generated image pin here unless a reviewed release/rollback procedure explicitly assigns that ownership. Do not use direct `kubectl` mutation as a permanent deployment. `spec.verify` is currently omitted from child GitRepositories, so `Signature: none` is expected; do not add signature verification without the signed-commit/key rollout.
