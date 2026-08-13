# Issue #4 evidence/postmortem — implementation review

- **Record status:** reviewed implementation limitation; production execution is
  not claimed.
- **Environment:** native production `belacca-native`.
- **Review scope:** runbook, safety gate, evidence schema, and CI validation
  added by issue #4.
- **Production drill window:** not started.
- **Sanitization:** no production output, credentials, private telemetry,
  player data, room IDs, or client addresses are included.

## Summary

The previous game-day document did not cover native production. This change
ports the six requested drill contracts to native production and adds explicit
fail-closed checks for the native context and protected PVC names. It also
provides a machine-readable evidence record with detection, acknowledgement,
mitigation, recovery, user impact, component verification, RTO, and 99%
policy-comparison fields.

No production failure was injected from this worktree. In particular, this
record does not claim that an edge, k3s server, Longhorn replica, Pong API, or
Flux reconciliation was exercised. No synthetic recovery result is claimed.

## Findings and follow-up

| Area | Reviewed implementation status | Exact operator follow-up |
|---|---|---|
| Public edge | Native Traefik Pod restart is exact-name and peer-count guarded | Run Drill 1 with the named native context and approved edge node |
| Control plane | Three-server/etcd-quorum checks and provider-console procedure documented | Run Drill 2 with infrastructure owner and out-of-band host access |
| Pong/SQLite | Exact Pod restart checks `pong-api-data` and one-writer invariant | Run Drill 3 after independently verifying a quiesced backup artifact |
| Longhorn | Protected volumes are excluded; provider/Longhorn action is not faked | Run Drill 4 against an approved disposable test volume or maintenance operation |
| Flux rollback | Scope is limited to `cloudnativepong` and `flux-system/pong` | Run Drill 5 with reviewed failing and revert commits |
| Synthetic recovery | External-only status publisher contract; dashboard remains unconfigured | Run Drill 6 through the external status owner and correlate observation IDs |

## Policy comparison

There are no measured recovery seconds or failed external slots in this
implementation record. The applicable catalog RTO is 4 hours for the affected
public services. The 99%/30-day policy is not an achieved result: the status
repository requires a complete valid 720-hour window, and controlled drill
recovery is not availability arithmetic.

## Review gate

Before this record is replaced by a production result, the incident lead and
platform owner must confirm that the evidence JSON contains UTC timestamps,
exact resource scope, sanitized command evidence, component verification,
external synthetic correlation, measured `rto_met`, and the 99% policy
comparison. A reviewed record must never be marked successful solely because
`kubectl` or Flux responds; it must include application and external recovery.
