# OpenContracts runtime configuration

This directory contains examples only. Real WorkerKeys stay in the user's Harness secret store, host environment, or an untracked local env file.

## MVP MCP access

The MVP assumes OpenContracts is reachable only inside a trusted LAN/VPN/restricted network domain and keeps its corpuses public inside that deployment.

Set:

```text
OPENCONTRACTS_MCP_URL=https://<internal-host>/mcp/
```

No OAuth/Bearer credential is required for normal read-side MCP access in this mode. Network reachability is the confidentiality boundary.

Future deployments may move to private corpuses and `/mcp/me/` OAuth without changing the Skill behavior.

## Upload authentication

Formal contract ingestion uses a `CorpusAccessToken` / `WorkerKey` bound to the intended history corpus.

Recommended policy:

- revoke/rotate the key when a host is retired or the key is exposed;
- use expiry/rate limits when practical;
- do not send `add_to_corpus_id` from the helper: the WorkerKey binding selects the destination;
- never place real WorkerKeys in `SKILL.md` or committed configuration.

Contract-learning material is not uploaded to OpenContracts in MVP and therefore requires no second WorkerKey.

## HTTPS

OpenContracts `production.yml` includes a Traefik service exposing ports 80/443. The bundled Traefik config redirects HTTP to HTTPS and uses ACME/Let's Encrypt.

OpenContracts `local.yml` has no TLS proxy and exposes Django directly on port 8000.

For a LAN-only hostname, the upstream production Traefik example cannot be used unchanged if its HTTP ACME challenge is unreachable from the public Internet. In that case either adapt Traefik to your certificate source or put Caddy in front of the existing OpenContracts HTTP endpoint.

If using an internal CA, every Harness host must trust that CA; disabling certificate verification is not an accepted production configuration.
