# Native production cluster

## Status

This directory is the GitOps root for **native production**. It targets three
native k3s servers:

- `belacca-k3s-01` — `169.58.97.73`
- `belacca-k3s-02` — `169.58.143.41`
- `belacca-k3s-03` — `169.58.143.42`

The former `k3d-pong` application cluster on `.73` was retired after the
controlled state handoff. Its historical GitOps tree remains under
`clusters/vmi3474918/` for audit/reference and is not a second live owner.

**Native cutover: complete.** Native Flux, Longhorn, Traefik, cert-manager,
TLS, Pong, portfolio, analytics, Dex, Headlamp, and Flux Web are reconciled
and public DNS-only records for application hosts contain `.73`, `.41`, and
`.42`. Pong, GoatCounter,
and Dex state was restored into native Longhorn-backed single-writer PVCs.
Direct DNS is round-robin rather than health-aware failover; monitor both edges
and remove an unhealthy address manually if required.

## Current scope

Native production currently contains:

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

The native root and all child Kustomizations are Ready. Native cert-manager
owns a SOPS/age-encrypted Cloudflare DNS-01 credential, a ClusterIssuer, and
seven Ready Certificates. Native Traefik routes portfolio, Pong, Dex,
Headlamp, Flux Web UI, and analytics through private ClusterIP Services;
direct and public probes succeed on all three native edges (`.73`, `.41`, and
`.42`). A private native
Prometheus diagnostic child and Flux notification contract are now committed,
but external backup retention, authenticated browser completion, notification
destination provisioning, and live one-node failure measurements remain
hardening items. The approved native drill contract and pending evidence ledger
are in [`../../docs/NATIVE-FAILURE-DRILLS.md`](../../docs/NATIVE-FAILURE-DRILLS.md)
and [`../../docs/NATIVE-DRILL-EVIDENCE.json`](../../docs/NATIVE-DRILL-EVIDENCE.json);
node mutation remains owned by the infrastructure repository.
The public 99%/30d SLO is measured by the external status repository, not by
native Prometheus, and is not yet reportable until its complete window exists.

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
├── observability/ private Prometheus diagnostics and SLO-source contract
├── notifications.yaml native Flux notification contract (destination out of band)
├── native-sources.yaml       published application GitRepositories
└── native-applications.yaml  native app Kustomizations
```

The native root contains the application GitRepositories and application
Kustomizations described above, plus cert-manager DNS-01 resources in `tls/`
and portfolio/Pong Ingresses and redirect Middleware in `routing/`. It does
not contain the retired old-production ACME PVC or old local-path PVCs. Public
DNS is managed out of band at Cloudflare; additional hostnames or services
require a separate reviewed change.

## Safe inspection and render checks

The following are inspection examples for native production only. They do not
apply resources; the live workload status must be confirmed from Flux and
Kubernetes directly:

```bash
kubectl config use-context belacca-native
kubectl kustomize clusters/belacca-production >/tmp/native-production-render.yaml
kubectl get nodes
kubectl -n flux-system get gitrepositories,kustomizations
```

The old `k3d-pong` runtime is retired. Do not recreate it or apply old
production PVC/ACME recovery commands against native production. Use the
post-cutover hardening and manual DNS-removal procedures instead.

## Post-cutover hardening

Native cutover is complete. Remaining operator work is:

1. select a health-aware API/ingress VIP or load balancer instead of direct
   DNS round-robin;
2. configure encrypted external backups and complete an isolated restore
   rehearsal;
3. complete authenticated browser journeys and the approved one-node failure
   drills, then publish three comparable measurements; and
4. review the native Traefik UID 0 low-port-binding exception.

The retired old-production manifests and rollback history remain available for
reference, but the old k3d runtime is not a live rollback target.
