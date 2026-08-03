# vmi3474918 cluster

Flux reconciles this directory into the existing `k3d-pong` cluster.

- `flux-system/`: Flux controllers and root source bootstrap
- `sources.yaml`: independent application Git sources
- `applications.yaml`: application Kustomizations
- `routing/`: Traefik host/TLS routing
- `headlamp/`: private read-only cluster dashboard
- `traefik-acme-pvc.yaml` and `traefik-config.yaml`: persistent ACME and ingress configuration
