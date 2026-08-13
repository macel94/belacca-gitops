# Native production operations

Native production is the only maintained platform plane. Flux reconciles
`clusters/belacca-production/` into the three-server k3s cluster identified by
the `belacca-native` context. It owns public routing, application sources,
cert-manager, Longhorn, observability, notifications, and operator surfaces.

## Operating rules

- Use the `belacca-native` context and verify its API endpoint before mutation.
- Make production changes through reviewed Git commits and Flux reconciliation.
- Preserve protected PVCs, namespaces, secrets, and single-writer SQLite state.
- Keep native edge, API, storage, and control-plane ports within the documented
  firewall boundary.
- Use isolated disposable targets for restore rehearsals, capacity tests, and
  chaos experiments; never use native production as a test sandbox.

## Deployment validation

The native root and every child Kustomization are rendered in CI. Catalog,
recovery, notification, observability, privacy, and secret-safety validators
must pass before merge. Flux source and application revisions, readiness,
public health, storage health, and user-journey evidence are checked after
reconciliation.

## Recovery

Native incidents use the incident lifecycle, native game-day drills, and
reviewed Git rollback. Recovery evidence records approval, owner, timestamps,
user impact, exact checks, rollback, and limitations. Native production is the
only production target.
