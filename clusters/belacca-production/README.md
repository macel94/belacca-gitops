# Native staging cluster

## Status

This directory is the GitOps root for **native staging**, not old production.
Native staging targets three native servers:

- `belacca-k3s-01` — `169.58.97.73`
- `belacca-k3s-02` — `169.58.143.41`
- `belacca-k3s-03` — `169.58.143.42`

The old production environment remains the existing
`k3d-pong` cluster, reconciled from `clusters/vmi3474918/`, and publicly
addressed at `169.58.97.73`.

**Native cutover: not started.** No old production workload inventory has been
adopted by this tree. Pong and portfolio Kustomizations are published through
the native root, with native-only Traefik routes and cert-manager Certificates
now staged for those deployed services. Do not point old production DNS at the
native server addresses or use old production rollback procedures against this
cluster.

## Current scope

Native staging currently contains:

- the Flux v2 bootstrap and controllers under `flux-system/`;
- the SOPS/age-encrypted Secret interfaces and target namespaces under
  `secrets/`;
- the Longhorn storage foundation under `longhorn/`;
- Flux-managed Traefik under `edge/`;
- the cert-manager controller and CRDs under `cert-manager/`, plus the native
  Cloudflare DNS-01 ClusterIssuer and application Certificates under `tls/`;
  and
- published Pong and portfolio Kustomizations plus their native Traefik routes
  under `routing/`, sourced by `native-sources.yaml`.

The native root and the `pong`/`portfolio` child Kustomizations are Ready.
Their workloads have no old-production PVC ownership. Native cert-manager
now owns a SOPS/age-encrypted Cloudflare DNS-01 credential, a ClusterIssuer,
and Certificates only for the deployed portfolio and Pong services. Native
Traefik routes only target those two services. Dex, Headlamp, Flux Web UI,
GoatCounter, analytics, observability, and their hostnames remain undeployed.
No public DNS changes, application SLO, backup guarantee, or notification
coverage is established by this tree.

The native Flux bootstrap uses the native context/cluster identity
`belacca-native`. Flux owns decryption and reconciliation; plaintext Secret
values and the SOPS/age private key remain outside Git. Do not apply encrypted
Secret files manually.

## Directory map

```text
clusters/belacca-production/
├── flux-system/  Flux controllers and native root bootstrap
├── secrets/      SOPS/age-encrypted interfaces and target namespaces
├── longhorn/     native storage foundation; not yet an application migration
├── edge/         Flux-managed Traefik
├── cert-manager/ cert-manager controller and CRDs
├── tls/          encrypted Cloudflare DNS-01 and app Certificates
├── routing/      native portfolio and Pong Traefik routes
├── native-sources.yaml       published application GitRepositories
└── native-applications.yaml  native app Kustomizations
```

The native root contains the two application GitRepositories and application
Kustomizations described above, plus cert-manager DNS-01 resources in `tls/`
and portfolio/Pong Ingresses and redirect Middleware in `routing/`. It does
not contain old production routing, old production ACME PVC ownership, or old
production database/PVC resources. It does not change public DNS. Additional
hostnames or services require a separate reviewed native cutover plan.

## Safe inspection and render checks

The following are inspection examples for native staging only. They do not
apply resources; the live workload status must be confirmed from Flux and
Kubernetes directly:

```bash
kubectl config use-context belacca-native
kubectl kustomize clusters/belacca-production >/tmp/native-staging-render.yaml
kubectl get nodes
kubectl -n flux-system get gitrepositories,kustomizations
```

Do not run old production commands such as `kubectl config use-context
k3d-pong`, old production PVC recovery, or old production ACME rollback against
native staging unless a future migration runbook explicitly changes the
context and ownership contract.

## Future cutover gate

Native cutover remains **not started**. Before native staging could become an
application target, operators must separately review and validate:

1. all three native server identities and the `.41`/`.42` network addresses;
2. Flux bootstrap, SOPS/age decryption, CNI, ingress, and Longhorn health;
3. application renders and ownership boundaries for each workload;
4. protected old production PVC and ACME rollback procedures;
5. DNS, certificate, SSO, notification, backup, observability, and public-route
   contracts, including an out-of-band Cloudflare credential and narrowly
   scoped DNS-01 plan; and
6. a staged ownership transfer with pruning disabled before any old production
   resource is moved.

Until those gates are complete, old production is the only environment covered
by the application runbooks in [`../../docs/SITES.md`](../../docs/SITES.md),
[`../../docs/RELIABILITY.md`](../../docs/RELIABILITY.md), and
[`../../MIGRATION.md`](../../MIGRATION.md).
