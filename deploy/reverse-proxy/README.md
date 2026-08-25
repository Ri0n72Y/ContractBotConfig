# OpenContracts HTTPS choices

OpenContracts has two relevant Compose modes:

## `production.yml`

`production.yml` already includes a `traefik` service and exposes host ports 80/443. The bundled Traefik configuration redirects HTTP to HTTPS and uses ACME/Let's Encrypt.

Use the bundled Traefik when its certificate model fits the deployment. For a LAN-only host, the checked-in HTTP ACME challenge will not work unchanged when Let's Encrypt cannot reach the service from the Internet. In that case adapt Traefik to the organization's DNS/PKI or provide static certificates.

## `local.yml`

`local.yml` exposes Django directly on port 8000 and does not include an HTTPS reverse proxy.

If the current deployment uses `local.yml`, Caddy is the simplest MVP TLS wrapper:

```text
Harness
  → https://contracts.internal.example
  → Caddy
  → http://opencontracts-host:8000
```

`Caddyfile.example` is provided for that path.

## Internal certificates

For an internal-only DNS name, use either:

- an organization-managed certificate/internal PKI; or
- Caddy `tls internal` and distribute/trust the Caddy root CA on every Harness host.

Keep TLS verification enabled. Do not use `verify=False`, `-k`, or equivalent as the normal deployment configuration.

## Nginx

The Nginx sample remains available for environments already standardized on Nginx, but Caddy is preferred when adding a minimal TLS wrapper to a `local.yml` deployment.
