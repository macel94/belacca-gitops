# vmi3474918 cluster

Flux reconciles this directory into the existing `k3d-pong` cluster.

- `flux-system/`: Flux controllers and root source bootstrap
- `sources.yaml`: independent application Git sources
- `applications.yaml`: application Kustomizations
- `routing/`: Traefik host/TLS routing
- `headlamp/`: read-only Headlamp dashboard with Google OAuth2 Proxy
- `analytics/`: self-hosted GoatCounter with a protected SQLite database
- `traefik-acme-pvc.yaml` and `traefik-config.yaml`: persistent ACME and ingress configuration

## Self-hosted analytics

GoatCounter is available at `https://stats.belacca.com/` after the DNS record
and Flux reconciliation are complete. It stores aggregate, cookie-free
analytics for the portfolio and uses its built-in country database. The
portfolio sends tracking requests through its own `/count` and `/count.js`
paths, so visitors do not contact a third-party analytics host. The dashboard
itself is protected by GoatCounter's login session.

Create the analytics namespace and administrator Secret before the first Flux
reconciliation. The password is read interactively and is never stored in Git:

```bash
kubectl create namespace analytics --dry-run=client -o yaml | kubectl apply -f -
read -rsp 'GoatCounter admin password: ' GC_PASSWORD; echo
kubectl -n analytics create secret generic goatcounter-admin \
  --from-literal=email=francesco.belacca@hotmail.it \
  --from-literal=password="$GC_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
unset GC_PASSWORD
```

The StatefulSet init container then creates the initial site and administrator
idempotently with the exact hostname used by the ingress. Wait for it with:

```bash
kubectl -n analytics rollout status statefulset/goatcounter
```

The GoatCounter login cookie applies only to the dashboard user; portfolio
visitors receive no analytics cookie. Keep the `goatcounter-admin` Secret out
of Git. If you change it later, update the password through the dashboard or
run the documented password-management command rather than assuming a Secret
change alone changes the existing account.

The database is on the `goatcounter-data` PVC and the StatefulSet intentionally
has one replica because SQLite is single-writer and the cluster's `local-path`
storage is node-local. Create a consistent backup before upgrades or storage
work:

```bash
backup="goatcounter-data-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
kubectl -n analytics exec statefulset/goatcounter -- \
  goatcounter db query -format=exec \
  "VACUUM INTO '/tmp/goatcounter-backup.sqlite3'"
kubectl -n analytics cp \
  goatcounter-0:/tmp/goatcounter-backup.sqlite3 "$backup"
kubectl -n analytics exec statefulset/goatcounter -- \
  rm -f /tmp/goatcounter-backup.sqlite3
```

Add this DNS record before expecting the Let's Encrypt certificate:

```text
stats.belacca.com  A  169.58.97.73
```
