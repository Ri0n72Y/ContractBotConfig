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

Formal contract ingestion still uses a `CorpusAccessToken` / `WorkerKey` bound to the intended history corpus. Learning uploads use a second WorkerKey bound to `learning-inbox`.

Recommended policy:

- keep the two write keys separate;
- revoke/rotate keys when a host is retired or a key is exposed;
- use expiry/rate limits when practical;
- do not send `add_to_corpus_id` from the helper: the WorkerKey binding selects the destination;
- never place real WorkerKeys in `SKILL.md` or committed configuration.

## HTTPS

HTTPS is still recommended on the LAN because WorkerKeys and contract contents are transmitted over the connection.

OpenContracts' production tree includes Traefik with HTTPS and Let's Encrypt. For an internal-only hostname, a small Caddy/Nginx reverse proxy or an adapted Traefik configuration is usually simpler than using the upstream public-domain example unchanged.

If using an internal CA/self-signed certificate, every Harness host must trust that CA; disabling certificate verification is not an accepted production configuration.
