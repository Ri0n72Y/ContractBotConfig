# OpenContracts HTTPS for the MVP

The current deployment uses OpenContracts `local.yml` inside a trusted LAN/restricted network and does not use a public DNS name.

## Selected path: Caddy

`local.yml` exposes Django on host port 8000 and does not include an HTTPS reverse proxy. The MVP therefore uses Caddy as the canonical TLS entrypoint:

```text
WorkBuddy / Harness
  → https://contracts.internal.example
  → Caddy
  → http://127.0.0.1:8000
  → OpenContracts Django / MCP / REST API
```

Use `Caddyfile.example` as the starting point.

The Harness MCP URL becomes:

```text
https://contracts.internal.example/mcp/
```

Formal ingestion uses the same HTTPS origin, for example:

```text
https://contracts.internal.example/api/imports/documents/
```

## Internal certificate

Because the deployment does not use a publicly reachable domain, the example uses:

```caddy
tls internal
```

Caddy will issue the site certificate from its own local CA. Export/install the Caddy root CA into the trust store of every WorkBuddy/Harness machine that needs to connect. Keep TLS verification enabled.

If the organization later provides an internal-PKI certificate, replace `tls internal` with that certificate configuration without changing the Skill/MCP architecture.

## Frontend

This MVP Caddy configuration is intentionally scoped to the Django endpoint required by MCP, REST imports, GraphQL and admin APIs. OpenContracts' local frontend remains on its existing Vite/local development configuration.

If a later requirement calls for one HTTPS origin for both the browser UI and API, add explicit frontend routing after confirming the exact frontend port/configuration of the deployed OpenContracts revision.

## Host exposure

Caddy should be the network-facing entrypoint. Where practical, bind OpenContracts' raw local HTTP port to loopback or restrict port 8000 with the host firewall so LAN clients cannot bypass Caddy and send WorkerKeys/contracts over cleartext HTTP.

Nginx and bundled production Traefik are not part of the selected MVP deployment path.
