# Azure Without Azure native resources

This directory owns only the isolated PostgreSQL 18.6 StatefulSet and the
network policy boundary for the `azure-without-azure` application namespace.

The application Deployment, Service, namespace, and immutable image pin are
owned by the application repository and consumed through its Flux
`GitRepository`. Authentication is through the existing Dex installation; no
Keycloak is deployed here.

PostgreSQL 19 is not used because it remains beta in the current release
window. PostgreSQL 18.6 is pinned by digest until a reviewed stable-major
upgrade is available.
