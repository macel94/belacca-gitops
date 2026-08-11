> **Historical retired-runtime document.** This runbook describes the former
> k3d routing procedure and is retained for audit/history only. Current public
> routing is native production on `.73`, `.41`, and `.42`, with DNS-only Cloudflare
> round-robin records and Flux ownership under `clusters/belacca-production/`.
> Do not execute the retired k3d context commands.

# Adding a public subdomain

This historical runbook describes the former way to add or update a public
`*.belacca.com` hostname on the retired `k3d-pong` cluster. The canonical
inventory of currently supported sites and aliases is
[`docs/SITES.md`](docs/SITES.md). This runbook covers Cloudflare DNS, Traefik
HTTPS, Headlamp-style authentication, and Flux GitOps ownership.

The short version is:

1. Obtain a valid, narrowly scoped Cloudflare API token.
2. Create and verify the application DNS **before** exposing the route; the
   DNS-01 provider separately creates ACME TXT records in the zone.
3. Add the HTTP redirect and HTTPS route in this repository.
4. Keep credentials outside Git.
5. Commit and push the GitOps child repository, then update the parent gitlink.
6. Reconcile Flux and verify DNS, the certificate, authentication, and the
   backend.

## Repository and cluster model

- `belacca-platform` is the parent workspace.
- `belacca-gitops` is a gitlink/submodule and the cluster-level source of truth.
- Flux watches `belacca-gitops` and reconciles `clusters/belacca-production`.
- `clusters/belacca-production/routing/` owns current public host routing.
- Native Traefik is the ingress controller in `kube-system` on `.73`, `.41`, and `.42`.
- Cloudflare DNS-only records use all three native edge addresses.
- The retired Kubernetes context was `k3d-pong`; do not use it for production.

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

## Step 2: create DNS first (historical procedure; use native-production records)

Find the zone ID from the successful zone lookup, then list the exact record:

```bash
ZONE_ID='<zone-id>'
# For the portfolio www alias requested in this change:
HOST='www.francesco.belacca.com'
ORIGIN='169.58.97.73'
DNS_API="https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records"

curl -fsS -G \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-urlencode 'type=A' \
  --data-urlencode "name=${HOST}" \
  "${DNS_API}"
```

The former desired record for the retired cluster was:

```text
Type:    A
Name:    www.francesco.belacca.com
Content: 169.58.97.73
TTL:     300
Proxied: false
```

Use DNS-only (`proxied: false`) because native Traefik terminates TLS and
cert-manager uses the Cloudflare DNS-01 challenge. Native production uses two A
records, `.41` and `.42`; this historical single-origin example must not be
copied as-is. If an exact A record exists, update it rather
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

Verify public DNS before adding or relying on the HTTPS route. For the
portfolio alias in this change:

```bash
curl -fsS -H 'accept: application/dns-json' \
  'https://cloudflare-dns.com/dns-query?name=www.francesco.belacca.com&type=A'
curl -fsS -H 'accept: application/dns-json' \
  'https://dns.google/resolve?name=www.francesco.belacca.com&type=A'
```

Both should return `169.58.97.73`. Do not proceed to certificate verification
while the result is NXDOMAIN or points elsewhere. After DNS and Flux
reconciliation, verify the redirect while preserving a path:

```bash
curl -I https://www.francesco.belacca.com/reliability.html
# Expected: 308/301 Location: https://francesco.belacca.com/reliability.html
```

## Step 3: add GitOps routing (native production)

For current production, put the route in `clusters/belacca-production/routing/`.
The remaining examples below describe the retired layout and must be adapted
before use. For a normal public service,
add two Ingress objects:

1. `web` entrypoint: redirect HTTP to HTTPS.
2. `websecure` entrypoint: terminate TLS and route to the backend Service.

Use the existing `ingressClassName: traefik`, the existing
`letsencrypt` resolver, an explicit host, and an explicit Service port. Keep
middleware references namespace-qualified in Traefik's annotation format.

For the shared Google authentication, deploy Dex as a pinned HelmRelease with
persistent state. The canonical path-scoped issuer and Google connector callback
reuse the existing authorized dashboard callback:

```text
issuer:   https://dashboard.belacca.com/oauth2
callback: https://dashboard.belacca.com/oauth2/callback
```

`dex.belacca.com` remains a TLS-protected redirect alias for operators; it is
not the issuer used by the relying parties.

Each application uses a separate Dex client. Headlamp and analytics use pinned
OAuth2 Proxy HelmReleases whose upstreams are the private Headlamp and
GoatCounter Services; Flux Web UI uses its own Dex client. The dashboard and
analytics proxy `authenticatedEmailsFile` contains only `belakkuz@gmail.com`.
The public GoatCounter collector paths `/count`, `/count.js`, and `/status`
remain direct routes so portfolio analytics does not require a browser login.

Keep Google client credentials, Dex client secrets, and OAuth2 Proxy cookie
secrets in out-of-band Secrets. The charts reference those Secret names by
key, not contain their values. GoatCounter itself still uses its own
application session cookie after the edge Dex gate because the upstream does
not consume OAuth2 Proxy identity headers; its existing admin user is aligned
to `belakkuz@gmail.com` and its password remains out of band.

The Secret must exist before the authenticated route is expected to work. Do
not commit the Google client secret, cookie secret, OAuth client JSON, or a raw
Secret manifest containing any of them. Record only the Secret name and
rotation procedure in documentation. A namespace-local Traefik BasicAuth
middleware may remain as a rollback path during the migration, but it should
not be the active route after OAuth2 Proxy is verified.

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

## Step 4: use the committed ACME configuration

This cluster currently uses Traefik DNS-01 with Cloudflare, as committed in
`clusters/vmi3474918/traefik-config.yaml`:

```yaml
certificatesResolvers:
  letsencrypt:
    acme:
      storage: /data/acme.json
      dnsChallenge:
        provider: cloudflare
        resolvers:
          - 1.1.1.1:53
          - 8.8.8.8:53
envFrom:
  - secretRef:
      name: traefik-cloudflare
```

The out-of-band `kube-system/traefik-cloudflare` Secret must contain the
`CLOUDFLARE_DNS_API_TOKEN` key with a narrowly scoped token that can edit DNS
for the `belacca.com` zone. Do not commit the Secret, its token, or a guessed
DNS provider endpoint. The existing `traefik-acme` PVC and `/data/acme.json`
remain protected state.

DNS-01 requires:

- The hostname's DNS zone is hosted by the configured Cloudflare account.
- The Secret exists before Traefik attempts issuance or renewal.
- The token can read the zone and edit the required TXT records.
- Public DNS points the application hostname at the cluster for normal HTTPS.
- Public TCP port 443 reaches Traefik's `websecure` entrypoint for normal TLS.

Port 80 and the ordinary HTTP-to-HTTPS redirect are not the ACME challenge
path for this configuration. Do not change the challenge mechanism without
changing the manifest and this runbook in the same reviewed change. Never
delete `acme.json` or the ACME PVC to recover from a challenge error; fix
DNS/token/configuration and reconcile.

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
curl -I https://<hostname>/oauth2/start
```

For the Google OAuth2 Proxy route, expect:

- HTTP: `301` or `308` to HTTPS.
- HTTPS at `/`: a redirect to `/oauth2/start` or the Google authorization endpoint.
- `/oauth2/start`: a redirect to `https://accounts.google.com/...`.
- After an allowed Google login: a `200` Headlamp response.
- A Google account not in the allowlist: rejection by OAuth2 Proxy, not Headlamp.

During a staged rollout, the old BasicAuth route may remain active until the
OAuth2 Proxy Deployment and HelmRelease are Ready. Switch the Ingress backend
only after that readiness check.

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

## Shared Dex/Google SSO notes

Dex is the shared OIDC issuer for Flux Web UI, Headlamp OAuth2 Proxy, and the
analytics OAuth2 Proxy. Its canonical issuer is:

```text
https://dashboard.belacca.com/oauth2
```

The existing Google web client authorizes exactly this connector callback:

```text
https://dashboard.belacca.com/oauth2/callback
```

Use the path-scoped Dex issuer for proxies, scopes `openid email profile`, and
allow only the intended email address. OAuth2 Proxy's upstreams are private ClusterIP
Services. Headlamp's in-cluster mode uses one backend ServiceAccount, so the
separate `headlamp-authenticated-admin` binding grants that backend
`cluster-admin`; never expose the ServiceAccount or remove the exact proxy
allowlist/network policy.

Deploy Dex and wait for its HelmRelease/Deployment to be Ready before relying on
application SSO. Then reconcile the Flux Web UI and OAuth2 Proxy releases and
wait for their Deployments before switching/validating the HTTPS routes. The
old Headlamp BasicAuth Secret and middleware remain a rollback path until the
Dex route, callback, certificate, and allowed-email behavior are verified.

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
- Remove or rotate the out-of-band Google OAuth Secret when access is no longer
  required.
- Remove the old BasicAuth Secret only after the Dex/OAuth login paths have been
  verified and the rollback window has ended.
- Revoke the temporary Cloudflare token after DNS work completes.

## References

- Cloudflare DNS API: <https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/create/>
- Traefik ACME: <https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/>
- Flux Kustomizations: <https://fluxcd.io/flux/components/kustomize/kustomizations/>
