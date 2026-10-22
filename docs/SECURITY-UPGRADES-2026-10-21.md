# October 2026 security upgrade preparation

Status: **eligible cluster upgrades delivered through GitOps on October 22**;
Longhorn, Vault and live host maintenance remain deferred as detailed below.
Versions/digests were checked against official releases, Helm indexes or anonymous
OCI metadata on October 21. Application publication and rollout are separate
steps; successful application publishers own their generated deployment commits.

## Delivery evidence

- Flux 2.9.6: `bc3f088`; ownership migration: `9a92726`. The supported
  `--override-manager=flux` option migrates bootstrap SSA ownership. All four
  controllers now have no CPU limit, with requests/memory limits preserved.
  An explicit-null experiment was rejected in server dry-run and never pushed.
- Kyverno: `b6898ec`; all four enforcing ClusterPolicies report Ready.
- Traefik/cert-manager: `3401212`; three edge DaemonSet pods healthy, all
  certificates Ready and direct TLS health checks on all three public IPs pass.
- Redis/monitoring/backup runtimes: `9ee6dcf`; Redis, Prometheus, Alertmanager
  and backup-metrics workloads recovered. Future scheduled backup runs still
  need observation; today's successful backups/restores predate this wave.
- OAuth proxies, Headlamp and Flux Web: `b850a87`. Analytics' previously unpinned
  image was being rejected by immutable-image admission; the chart post-render
  digest resolves that failure without weakening policy.
- Dex: `a0bb32d`; deployed only after the October 22 02:41 backup and 03:59
  restore verification succeeded. Rollout and issuer discovery passed.
- GitOps CI passed for every wave above. No host package installation, k3s
  restart, SSH change, Tailscale enrollment or direct workload mutation ran.

**Longhorn 1.12.1 remains deferred**: preflight found ten healthy attached
volumes and healthy running replicas, but no Longhorn Backup/BackupVolume records
and all listed snapshots reported `readyToUse: false`. The three application
SQLite backup/restore jobs are not proof of recovery for every volume. Keep
1.12.0 until a verified recovery point exists for the affected state; do not
bypass this gate merely to finish a version checklist.

## Prepared cluster targets

| Component | Existing | Prepared target |
|---|---|---|
| Flux distribution | 2.9.3 labels | 2.9.6; regenerated CRDs/controllers and scoped NetworkPolicies |
| Traefik | 3.7.10 / chart 41.2.0 | 3.7.16 / chart 42.1.2; immutable image digest |
| Kyverno | 1.18.2 / chart 3.8.2 | 1.19.2 / chart 3.9.2; CRDs updated with the chart |
| cert-manager | 1.21.1 | 1.21.2; all five component digests refreshed |
| OAuth2 Proxy, both instances | 7.15.3 / chart 10.7.0 | 7.15.5 / chart 10.7.1; post-render digest pins |
| Headlamp | 0.44.0 | 0.46.0; post-render digest pin |
| Dex | 2.44.0 / chart 0.24.1 | 2.46.1 / chart 0.26.0; explicit patched image digest |
| Flux Web/Operator | 0.59.0 | 0.61.0; OCI chart pinned by manifest digest |
| Redis | 7.4.2-alpine | 7.4.11-alpine; same 7.4 branch and existing PVC/password |
| Prometheus | 3.13.2 | 3.13.5; same branch, immutable image and matching promtool checksum |
| Alertmanager | 0.33.1 | 0.34.1; immutable image; existing single-writer storage strategy |
| Backup/restore/metrics Python | 3.13.11-slim-bookworm | 3.13.16-slim-bookworm; one shared verified digest |
| Longhorn | 1.12.0 | 1.12.1 candidate deferred; active pin remains 1.12.0 |

The Flux bootstrap regeneration also restores namespace isolation for the event
server: cross-namespace webhooks are limited to port 9292, not event port 9090.
The Kustomization retains the existing no-CPU-limit policy for the four
controllers while keeping their CPU requests and memory limits unchanged.

Headlamp remains behind its OAuth2 Proxy boundary and retains its read-only
ClusterRole. No trusted-IP or skip-auth exemptions were added. No public service,
NodePort or ingress route was added. Traefik stays a host-network DaemonSet with
one edge unavailable at a time; its Kubernetes 1.30+ chart requirement is met by
the existing 1.35 cluster. Hub-only chart breaking changes do not apply because
Traefik Hub is not enabled.

Kyverno 1.19 is the final branch supporting the existing legacy ClusterPolicy
API; do not jump to 1.20 without a separate policy migration. Its chart-managed
CRDs remain enabled and Helm install/upgrade explicitly uses CreateReplace.

## Owning application and host repositories

- `cloudnativepong`: Caddy 2.11.7, final builders Go 1.27.3, patched `x/net` 0.60.0 and its
  required crypto/sys/text updates, refreshed distroless digest, and updated
  Alpine CA/timezone pins. CI and the module toolchain use Go 1.26.10. The
  existing publisher must generate the native/compatibility deployment pins.
- `francesco-belacca-site`: Caddy 2.11.7 plus build-time Alpine security updates.
  Both repositories rebuild the standard Caddy modules from locked nested Go
  modules with final Go 1.27.3 builders and `x/net` 0.60.0: the official Caddy 2.11.7 image
  still embeds Go 1.26.8 and `x/net` 0.59.0, affected by GO-2026-6610. A tag bump
  alone is insufficient. Build-only toolchain switching is disabled, standard
  modules/timezone support are retained, and runtime file capabilities remain
  absent. The site publisher must generate its image/deployment commit.
- `mutandae`: Go 1.27.3 and a digest-pinned/refreshed Alpine 3.24 runtime; the
  owning application publisher must generate its deployment image commit.
- `belacca-infrastructure`: guarded serial host package updates, k3s
  v1.35.9+k3s1 and install-only Tailscale 1.104.2. Public SSH on TCP 22 and the
  existing SSH/firewall settings must remain unchanged. See its maintenance
  runbook for approval and later client/tailnet enrollment.

Do not manually change workflow-generated application image pins in this repo or
in the application deployment overlays. Parent submodule gitlinks are not a
production deployment trigger. The separate `/root/sources/mutandae` worktree
has unrelated user changes and is not part of these source edits.

## Explicit deferrals / remaining gates

- **Vault 1.21.4 is not silently upgraded to 2.x.** It needs an independently
  verified Raft snapshot/restore and a reviewed major-version migration,
  including root/rekey endpoint authentication and the unseal sidecar. Existing
  storage, Secrets and NetworkPolicies are retained. It remains a known security
  follow-up, not a claim of being patched by this batch.
- PostgreSQL 17.11 and GoatCounter 2.7.0 were already at their verified current
  release targets; their existing immutable references are retained.
- Longhorn 1.13 exists, but a storage minor upgrade is not necessary for this
  same-line security pass. Never select the 1.12.2 prerelease as a production fix.
- Regenerating Flux/Helm manifests does not prove new application images pass
  vulnerability/SBOM/provenance admission gates. Keep those checks enabled and
  treat a newly disclosed upstream-image vulnerability as a blocker, not a reason
  to broaden VEX exceptions.
- The application repos now record an exact-version OpenPGP absence review for
  `x/crypto` 0.57.0, retiring the legacy scopes rather than adding version ranges.
  Go 1.27.3 production import graphs exclude all OpenPGP subpackages and Docker
  builds reject their introduction. Other findings remain blocking as required.
  All three application decision scripts now count fix-available HIGH/CRITICAL
  findings: a published patch is not evidence that the installed binary is fixed.
  See each application's security review and publisher artifacts.
- The host's older standalone Go installation and VM 01 SSH password/root-login
  hardening are not changed by the dedicated maintenance playbooks. Application
  compiler upgrades do not patch existing independently compiled host binaries.
- Native server kernels were already running 6.12.113 on October 21; no reboot
  is included. Existing vendor releases may contain dependencies awaiting newer
  upstream rebuilds; this batch is not a zero-vulnerability assertion.

## Safe promotion sequence, after explicit commit/push approval

Review each owning child diff. Commit/push source before running host playbooks.
Use separate reviewed promotion waves rather than committing every cluster-level
component into a simultaneous blind upgrade:

1. Flux bootstrap and namespace-isolation policy; verify all sources and child
   Kustomizations recover and notification delivery remains healthy.
2. Kyverno/chart CRDs; verify fail-closed image admission before promoting apps.
3. cert-manager and Traefik; verify issued certificates, all three public edges,
   redirects, Pong WebSockets and public health endpoints.
4. Redis and observability/backup runtime updates; verify Redis persistence and
   auth, single-writer volume attachment and the next backup/restore results.
5. Dex, OAuth2 Proxy, Headlamp and Flux Web; verify authenticated operator login
   and logout, callback URLs and rejection of anonymous API access. Dex's SQLite
   backup/restore must be current before its migration.
6. Longhorn's same-line patch, only with all active volumes/replicas healthy and
   a verified recovery point. Do not bypass instance-manager disruption budgets
   or delete/replace production PVCs.
7. Application source publishers, generated deployment commits, Flux revisions,
   workload digests, build markers and local/external journey verification.
8. Host updates/k3s/Tailscale via the infrastructure runbook in the approved
   maintenance context. Public SSH stays available throughout; no tailnet login
   or SSH lockdown is automated.

Put component-specific validators/CI version pins in the same wave as their
manifests; introduce the aggregate security-baseline test with the completed
baseline. Do not call a source change deployed until Flux's source revision,
applied revision, rollout and live behavior agree. No source Git signature
verification is claimed when `spec.verify` is omitted.

## Local verification

- Existing image, backup, catalog, Mutandae, recovery, network, notification and
  observability validators; all unittest suites; render every Kustomization.
- Render/lint old and target vendor Helm charts at Kubernetes 1.35.5, including
  Flux post-renderers. The cert-manager vendor chart uses a `v`-prefixed chart
  version that triggers Helm's existing SemVer warning; allow that warning only,
  not schema/template errors or unrelated warnings.
- Check the matching Prometheus promtool configuration, rules and rule tests.
- Test each owning application's source and local/disposable image health;
  never run experiments against native production or create debug pods.
- Run infrastructure syntax/unit checks and read-only/check-mode host preflights.

Local results: all GitOps workflow run steps, vendor Helm renders/lints,
Prometheus checks, infrastructure tests/syntax and Tailscale check mode passed.
Pong and Mutandae unit/race/vet checks passed with their prepared toolchains;
Pong was retested after the HTTP/2 dependency update. All three Caddy images
were rebuilt and their actual Go 1.26.10 / `x/net` 0.60.0 / Caddy 2.11.7 metadata
verified. The upgraded Pong API/static/gateway stack passed 23 Chromium checks
on a private disposable network with only a random loopback port published.
Portfolio dependency-degradation and health checks passed on disposable targets.
These are not native rollout or complete publisher vulnerability-scan results.

Do not run the default `npm test` browser target on this VM: native Traefik owns
localhost:8080 and Playwright can reuse it. An unintended default-target attempt
returned wrong-service/404 failures and timed out; no test process remained.
The successful browser runs explicitly disabled automatic web-server startup and
used a separate loopback fixture. Mobile/WebKit checks remain for publisher CI.

Public references: [Flux](https://github.com/fluxcd/flux2/releases/tag/v2.9.6),
[Traefik](https://github.com/traefik/traefik/releases/tag/v3.7.16),
[Kyverno](https://github.com/kyverno/kyverno/releases/tag/v1.19.2),
[Kyverno upgrade guide](https://kyverno.io/docs/installation/upgrading/),
[cert-manager](https://github.com/cert-manager/cert-manager/releases/tag/v1.21.2),
[OAuth2 Proxy](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.5),
[Headlamp](https://github.com/kubernetes-sigs/headlamp/releases/tag/v0.46.0),
[Dex](https://github.com/dexidp/dex/releases/tag/v2.46.1),
[Redis 7.4](https://raw.githubusercontent.com/redis/redis/7.4/00-RELEASENOTES),
[Prometheus](https://github.com/prometheus/prometheus/releases/tag/v3.13.5),
[Longhorn](https://github.com/longhorn/longhorn/releases/tag/v1.12.1),
[Go release history](https://go.dev/doc/devel/release),
[HTTP/2 advisory](https://pkg.go.dev/vuln/GO-2026-6610),
[Caddy build guidance](https://caddyserver.com/docs/build),
[Node.js October fixes](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases).
