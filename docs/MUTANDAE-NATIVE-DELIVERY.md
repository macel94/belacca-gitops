# Mutandae native-production delivery

This record documents the cluster-side delivery of Mutandae through the
private `belacca-gitops` repository and Flux on the `belacca-native` K3s
cluster.

For the source-side build and attestation history, see the Mutandae source
repository's [`docs/native-production-delivery.md`](https://github.com/macel94/mutandae/blob/main/docs/native-production-delivery.md).

## Ownership and final resources

- Owning source repository: private `macel94/mutandae`.
- Owning cluster repository: `macel94/belacca-gitops`.
- Cluster context: `belacca-native`.
- Flux source: `flux-system/mutandae`.
- Flux Kustomization: `flux-system/mutandae`.
- Application path: `./deploy/k3s`.
- Runtime namespace: `mutandae`.
- GitOps namespace owner: `clusters/belacca-production/mutandae/namespace.yaml`.
- Routes: `clusters/belacca-production/routing/mutandae-ingress.yaml`.
- Certificate: `clusters/belacca-production/tls/mutandae-certificate.yaml`.
- Admission policies:
  - `policies/first-party-image-provenance.yaml`;
  - `policies/first-party-image-sbom.yaml`;
  - `policies/first-party-image-vulnerability.yaml`;
  - `policies/production-image-digest.yaml`.
- Final GitOps commit: `7eaaa96`.

The live application source revision is the generated source deployment commit
`7347e2a`, and the final runtime image is:

```text
ghcr.io/macel94/mutandae:sha-4ed7eb016df617ca485ec3ed0e4d7e58578b1061@sha256:da80aaa6a6b277b583d28e8b15fa579b05f6f6ca4b5b3a43ca8734d9ea077b9d
```

The Flux revision and image source tag intentionally differ: Flux consumes the
generated deployment commit, while the image tag identifies the human source
commit that built the image.

## Problems and resolutions

### Private Flux source

The Mutandae source repository is private. Flux uses a dedicated read-only
GitHub deploy key stored in the encrypted `flux-system/mutandae-source-auth`
SOPS Secret. The GitOps repository contains no plaintext key or secret value.
The child GitRepository uses SSH and references that Secret.

### Runtime image access

The cluster does not use a GHCR pull Secret for Mutandae. The runtime package
is public, while the source repository remains private. This keeps runtime
pulling simple and prevents source access credentials from being reused as
registry credentials.

### Image pin ownership

The generated image tag and digest remain owned by the Mutandae source
repository's publish workflow. The GitOps repository owns the namespace,
routing, TLS, Flux source, and cluster policy, but does not manually edit the
application's generated image pin.

### Namespace and reconciliation ordering

The application Kustomization declares the application namespace in its source
manifest, but GitOps owns the namespace in native production. The application
overlay does not claim namespace ownership. The root Kustomization includes the
Mutandae namespace before namespaced TLS and routing resources are reconciled.

This avoids namespace ownership conflicts and prevents certificate/route
resources from being applied before their namespace exists.

### Attestation format mismatch

The working `belacca.com` and `pong` applications use GitHub Artifact
Attestations and therefore use Kyverno's `SigstoreBundle` verifier. Mutandae
could not use that GitHub storage path from its private user-owned source
repository, so Mutandae uses keyless Cosign attestations stored with the public
GHCR image.

The first Mutandae policy incorrectly tried the GitHub bundle verifier and
reported no matching signatures. Switching the outer verifier to `Cosign` was
necessary, but the newer Cosign OCI bundle layout still was not discoverable
through GHCR's OCI 1.1 referrer endpoint in the installed Kyverno path.

The final source workflow explicitly publishes legacy Cosign attachments:

```text
--new-bundle-format=false
--use-signing-config=false
```

The final GitOps policies use the standard Kyverno Cosign verifier:

```yaml
type: Cosign
```

`cosignOCI11` is intentionally not enabled. The proven legacy path is used
until a future Kyverno/Cosign/GHCR OCI 1.1 migration is tested end to end.

### Predicate matcher compatibility

The final policy matchers use the canonical predicate URIs:

```yaml
https://slsa.dev/provenance/v1
https://cyclonedx.org/bom
https://belacca.com/attestations/vulnerability/v1
```

The SBOM command-line alias `cyclonedx` is not the policy value; Cosign emits
the URI `https://cyclonedx.org/bom` in the in-toto statement.

The policies use the modern attestation `type` field. The old
`predicateType` field is retained only in the unrelated GitHub Artifact
Attestation rules for existing applications, where it is part of the current
working contract.

### SLSA predicate shape

A failed iteration passed a complete in-toto statement to `cosign attest`.
Cosign then wrapped that statement and Kyverno saw `buildDefinition` at the
wrong nesting level. The source workflow now passes only the SLSA predicate
object. Kyverno can therefore enforce:

```yaml
key: "{{ buildDefinition.buildType }}"
value: https://actions.github.io/buildtypes/workflow/v1
```

The final image's legacy `.att` artifact was decoded and confirmed to contain
three DSSE layers with flat, valid predicates.

### Flux retry and webhook behavior

A transient Kyverno webhook `EOF` caused Flux's root Kustomization to enter a
retry state. The correct recovery was to inspect Kyverno readiness and Flux
conditions, then reconcile the root and dependency chain after the webhook was
healthy. No permanent direct `kubectl apply`, `kubectl set image`, or admission
bypass was used.

## TLS, DNS, and routing

Both hostnames point to the three native edge IPs as Cloudflare DNS-only A
records:

```text
169.58.97.73
169.58.143.41
169.58.143.42
```

The existing native contracts are reused:

- ClusterIssuer: `letsencrypt-cloudflare`;
- Cloudflare Secret: `cert-manager/cert-manager-cloudflare`;
- DNS-01 solver: Cloudflare;
- Traefik: HTTP redirect and HTTPS Ingresses;
- Certificate Secret: `mutandae/mutandae-tls`.

No new Cloudflare Secret is stored in Git. The final certificate includes:

```text
mutandae.com
preview.mutandae.com
```

Both hostnames route to the same `mutandae` Service. Separate preview
application semantics were not requested, so preview currently serves the same
application rather than redirecting to the canonical hostname.

## Verification record

The final rollout was verified with:

```bash
flux get sources git -A | grep -E 'mutandae|flux-system'
flux get kustomizations -A | grep -E 'mutandae|native-image-policy|flux-system'

kubectl -n mutandae get deployment,pods,service,ingress,certificate -o wide
kubectl -n mutandae get deployment mutandae -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Final results:

```text
flux-system/mutandae GitRepository:  Ready
flux-system/mutandae Kustomization:  Ready=True, Healthy=True
mutandae Deployment:                 Available=True
mutandae Pod:                        1/1 Running
mutandae Certificate:                Ready=True
```

Public behavior:

```text
http://mutandae.com/          -> 301 https://mutandae.com/
http://preview.mutandae.com/  -> 301 https://preview.mutandae.com/
https://mutandae.com/         -> 200
https://preview.mutandae.com/ -> 200
```

The existing `belacca.com` endpoint was checked after the Mutandae rollout and
remained operational.

## Future Kyverno decision

Do not remove Kyverno. This cluster currently has four ClusterPolicies and
Kyverno enforces provenance, SBOM, vulnerability decision, and immutable digest
requirements for native workloads. Removing it would create a larger security
regression than the compatibility issue solved here.

The cluster currently runs Kyverno `v1.18.2` from chart `3.8.2`. The latest
stable release observed during this delivery is still `v1.18.2`; `v1.19.0`
release candidates exist but are not a production upgrade recommendation by
themselves.

A future upgrade is possible and should be performed through the existing Flux
HelmRelease. Before changing the production version or switching Mutandae to
OCI 1.1 attestations:

1. test the exact chart and app version in a staging/disposable cluster;
2. verify existing GitHub Artifact Attestation consumers (`belacca.com` and
   `pong`);
3. verify legacy Cosign attachments used by Mutandae;
4. test GHCR OCI 1.1 referrer discovery with the exact registry and Cosign
   versions;
5. reconcile all native child Kustomizations and confirm existing workloads;
6. only then consider enabling `cosignOCI11` or changing the source workflow.

The current legacy Cosign path is stable and should remain the production
contract until that migration has independent evidence.
