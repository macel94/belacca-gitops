# Adding a public subdomain

This runbook describes the supported way to add a public `*.belacca.com`
hostname to the existing `k3d-pong` cluster. It covers Cloudflare DNS, Traefik
HTTPS, Headlamp-style authentication, and Flux GitOps ownership.

The short version is:

1. Obtain a valid, narrowly scoped Cloudflare API token.
2. Create and verify DNS **before** asking Traefik for a certificate.
3. Add the HTTP redirect and HTTPS route in this repository.
4. Keep credentials outside Git.
5. Commit and push the GitOps child repository, then update the parent gitlink.
6. Reconcile Flux and verify DNS, the certificate, authentication, and the
   backend.

## Repository and cluster model

- `belacca-platform` is the parent workspace.
- `belacca-gitops` is a gitlink/submodule and the cluster-level source of truth.
- Flux watches `belacca-gitops` and reconciles `clusters/vmi3474918`.
- `clusters/vmi3474918/routing/` owns public host routing.
- Traefik is the existing ingress controller in `kube-system`.
- The public address is `169.58.97.73`.
- The Kubernetes context is `k3d-pong`.

Do not make a manual `kubectl apply` the permanent deployment. A manual apply
can be useful for server-side validation or short-lived diagnosis, but the
committed GitOps manifests must be the final owner of the resource.

## Credentials and token handling

Cloudflare API access is a prerequisite, not something that should be embedded
in a manifest or script committed to Git.

Use a token scoped to the `belacca.com` zone with only the permissions needed for
this operation, normally:

- `Zone - DNS - Read`
- `Zone - DNS - Edit`

If the API workflow is account-scoped, also confirm the intended Cloudflare
account ID. Do not put the token in a command-line argument, YAML file, shell
script, `.env` committed to the repository, or commit message. Prefer a hidden
prompt or a protected environment variable and unset it immediately afterward.

Example setup in a private shell:

```bash
read -rsp 'Cloudflare API token: ' CF_API_TOKEN
printf '\n'
export CF_API_TOKEN
export CF_ACCOUNT_ID='<account-id>'
```

Check the token without printing it:

```bash
curl -fsS \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  https://api.cloudflare.com/client/v4/user/tokens/verify
```

Then verify the actual zone operation. The zone lookup is the important
permission check for this workflow:

```bash
curl -fsS -G \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-urlencode 'name=belacca.com' \
  --data-urlencode "account.id=${CF_ACCOUNT_ID}" \
  https://api.cloudflare.com/client/v4/zones
```

A token can appear valid in one endpoint but still fail the zone operation due
to scope, account, or token state. Stop if the zone lookup does not return the
intended active zone. Never work around a `401` or `1000 Invalid API Token` by
loosening permissions blindly; issue a new correctly scoped token instead.

After the DNS change and verification, revoke or rotate the temporary token.

## Step 1: choose the hostname and backend

Before editing files, decide:

- Hostname, for example `dashboard.belacca.com`.
- Backend namespace and Service name.
- Backend Service port.
- Whether the backend is public or requires authentication.
- The required Kubernetes RBAC. Public BasicAuth does not replace Kubernetes
  authorization.

For an observation dashboard, keep the Service `ClusterIP`, use a dedicated
read-only ServiceAccount, and grant only `get`, `list`, and `watch` permissions
needed for health and logs. Do not grant create, update, delete, or Secret-read
permissions unless there is a separately reviewed requirement.

## Step 2: create DNS first

Find the zone ID from the successful zone lookup, then list the exact record:

```bash
ZONE_ID='<zone-id>'
HOST='dashboard.belacca.com'
ORIGIN='169.58.97.73'
DNS_API="https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records"

curl -fsS -G \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-urlencode 'type=A' \
  --data-urlencode "name=${HOST}" \
  "${DNS_API}"
```

The desired record for this cluster is:

```text
Type:    A
Name:    dashboard.belacca.com
Content: 169.58.97.73
TTL:     300
Proxied: false
```

Use DNS-only (`proxied: false`) because Traefik terminates TLS and this cluster
uses an ACME HTTP-01 challenge. If an exact A record exists, update it rather
than creating a duplicate. If it does not exist, create it:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  "${DNS_API}" \
  --data "{\"type\":\"A\",\"name\":\"${HOST}\",\"content\":\"${ORIGIN}\",\"ttl\":300,\"proxied\":false}"
```

If updating an existing record, use its record ID and `PUT` with the same
payload. Do not create both an A record and an unrelated CNAME for the same
name. Check for an unexpected AAAA record; Let’s Encrypt may try IPv6 if one is
published, so it must also reach the correct ingress or be removed.

Verify public DNS before adding or relying on the HTTPS route:

```bash
curl -fsS -H 'accept: application/dns-json' \
  'https://cloudflare-dns.com/dns-query?name=dashboard.belacca.com&type=A'
curl -fsS -H 'accept: application/dns-json' \
  'https://dns.google/resolve?name=dashboard.belacca.com&type=A'
```

Both should return `169.58.97.73`. Do not proceed to certificate verification
while the result is NXDOMAIN or points elsewhere.

## Step 3: add GitOps routing

Put the route in `clusters/vmi3474918/routing/`. For a normal public service,
add two Ingress objects:

1. `web` entrypoint: redirect HTTP to HTTPS.
2. `websecure` entrypoint: terminate TLS and route to the backend Service.

Use the existing `ingressClassName: traefik`, the existing
`letsencrypt` resolver, an explicit host, and an explicit Service port. Keep
middleware references namespace-qualified in Traefik's annotation format.

For an authenticated endpoint, create the BasicAuth Middleware in the same
namespace as the Ingress and reference an out-of-band Secret, for example:

```yaml
spec:
  basicAuth:
    secret: dashboard-basic-auth
    removeHeader: true
```

Create the Secret on the cluster without saving the generated YAML:

```bash
htpasswd -nB admin
kubectl -n <namespace> create secret generic dashboard-basic-auth \
  --from-literal='users=<username>:<bcrypt-hash>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

The Secret must exist before the authenticated route is expected to work. Do
not commit the password, bcrypt hash, or a Secret manifest containing either.
Record only the Secret name and rotation procedure in documentation.

Add the new file to the routing Kustomization:

```yaml
resources:
  - ...
  - dashboard-ingress.yaml
```

Validate before committing:

```bash
kubectl kustomize clusters/vmi3474918 >/tmp/platform-render.yaml
kubectl apply -f clusters/vmi3474918/routing/dashboard-ingress.yaml \
  --dry-run=server

git diff --check
```

## Step 4: use the working ACME configuration

This cluster currently uses Traefik HTTP-01 on the public `web` entrypoint:

```yaml
certificatesResolvers:
  letsencrypt:
    acme:
      storage: /data/acme.json
      httpChallenge:
        entryPoint: web
```

The K3s-packaged Traefik chart also receives the explicit argument:

```text
--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
```

Do not switch this cluster back to TLS-ALPN-01 without a specific, tested
reason. The existing Pong and portfolio certificates work, but during the
subdomain rollout the TLS-ALPN-01 request for the new hostname failed with
`remote error: tls: unrecognized name`. HTTP-01 succeeded after DNS was
published and the resolver was changed.

HTTP-01 requires:

- Public DNS pointing to the cluster.
- Public TCP port 80 reaching Traefik's `web` entrypoint.
- Public TCP port 443 reaching Traefik's `websecure` entrypoint for normal TLS.
- The ordinary HTTP-to-HTTPS redirect not blocking the ACME challenge router.

Traefik's ACME challenge router takes precedence over the ordinary redirect
router. Keep the redirect, but do not replace the ACME resolver with a custom
redirect service.

## Step 5: commit and reconcile in GitOps order

This repository uses a child GitOps repository plus a parent gitlink. Commit the
child first, push it, then update and push the parent pointer:

```bash
cd /root/sources/belacca-platform/belacca-gitops
git add clusters/vmi3474918/routing \
  clusters/vmi3474918/traefik-config.yaml \
  README.md
git diff --cached --check
git commit -m "Expose <hostname>"
git push origin main

cd ..
git add belacca-gitops README.md
git diff --cached --check
git commit -m "Publish <hostname>"
git push origin main
```

Before pushing, scan the staged and committed content for credentials. The
password, bcrypt hash, Cloudflare token, account credentials, and raw Secret
must not occur anywhere in Git.

Force reconciliation after the parent push:

```bash
kubectl config use-context k3d-pong
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization flux-system -n flux-system --with-source
flux reconcile kustomization belacca-routing -n flux-system --with-source
flux get kustomizations -A
```

Wait for the root and routing Kustomizations to report `Ready=True`. Do not
switch `prune` settings or move resource ownership in the same change unless
the migration procedure in `MIGRATION.md` has been followed.

## Step 6: verify the route and certificate

Check that the expected objects are owned by Flux:

```bash
kubectl -n <namespace> get ingress,middleware
kubectl -n <namespace> get ingress <https-ingress> -o yaml
```

Verify behavior:

```bash
curl -I http://<hostname>/
curl -I https://<hostname>/
curl -u '<username>:<temporary-password>' https://<hostname>/
```

For an authenticated route, expect:

- HTTP: `301` or `308` to HTTPS.
- HTTPS without credentials: `401` and a BasicAuth challenge.
- HTTPS with correct credentials: `200` from the dashboard/backend.
- HTTPS with an incorrect password: `401`.

Verify the certificate without suppressing hostname validation in the final
check:

```bash
echo | openssl s_client \
  -connect <hostname>:443 \
  -servername <hostname> 2>/dev/null | \
  openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

The SAN must contain the new hostname and the issuer should be Let’s Encrypt.
Also verify application-specific health and logs, and check RBAC explicitly:

```bash
kubectl auth can-i \
  --as=system:serviceaccount:<namespace>:<serviceaccount> \
  get pods --all-namespaces
kubectl auth can-i \
  --as=system:serviceaccount:<namespace>:<serviceaccount> \
  get pods/log --all-namespaces
kubectl auth can-i \
  --as=system:serviceaccount:<namespace>:<serviceaccount> \
  create deployments --all-namespaces
```

The first two should be `yes` when needed; mutation checks should be `no` for
an observation-only dashboard.

## What failed in the previous rollout

### Adding the route before DNS

The first route was applied while `dashboard.belacca.com` was NXDOMAIN. Traefik
immediately attempted ACME and Let’s Encrypt rejected it because no A or AAAA
record existed. After DNS was later created, the certificate was not acquired
until Traefik was restarted/reloaded to trigger a fresh attempt.

**Corrective rule:** create DNS, verify public resolution, and only then add or
activate the public HTTPS route. If an attempt already failed because of DNS,
fix DNS first and perform a controlled Traefik restart or configuration
reconciliation; do not delete `/data/acme.json` or the `traefik-acme` PVC.

### TLS-ALPN-01 for the new hostname

The existing configuration initially used TLS-ALPN-01. For the new hostname,
Let’s Encrypt reached port 443 but received `tls: unrecognized name` during the
challenge. Existing certificates for other hosts remained valid, which made
this look like a DNS problem even though public A resolution and TCP 443 were
working.

**Corrective rule:** use the tested HTTP-01 resolver on `web` for this cluster.
If a future change requires TLS-ALPN-01, test it with a new hostname in a
controlled change and confirm the challenge SNI path before relying on it.

### Cloudflare token failures

An earlier token produced `401` / `1000 Invalid API Token`. A later token also
failed token verification, but the actual zone API succeeded once the correct
account ID was supplied. This means both token verification and the intended
zone operation should be checked, and the zone operation must never be assumed
from token metadata alone.

**Corrective rule:** use a valid token with DNS Read/Edit for the exact zone,
query the zone by name and account, list the exact record, then create or update
idempotently. Never print the token in logs or responses. Rotate it immediately
after the change.

### Manual apply versus GitOps

Manual application was useful for immediate diagnosis, but it created temporary
cluster state before the GitOps commit was pushed. Flux later adopted the
resources after the child commit and parent gitlink were published.

**Corrective rule:** validate with `kubectl kustomize` and server-side dry-run,
then commit the manifests. If an emergency manual apply is unavoidable, apply
only the smallest resource set, record it, and reconcile GitOps immediately.
Do not leave a resource permanently managed outside Flux.

## Rollback and recovery

- Revert the routing commit and reconcile `belacca-routing`.
- Do not delete the ACME PVC or `/data/acme.json`; existing certificates are
  shared by the resolver.
- Do not delete application PVCs or recreate the cluster.
- If Flux ownership is being moved, follow `MIGRATION.md` and keep the old
  Kustomization at `prune: false` until the new owner is Ready.
- Remove or rotate the out-of-band BasicAuth Secret when access is no longer
  required.
- Revoke the temporary Cloudflare token after DNS work completes.

## References

- Cloudflare DNS API: <https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/create/>
- Traefik ACME: <https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/>
- Flux Kustomizations: <https://fluxcd.io/flux/components/kustomize/kustomizations/>
