# OpenContracts runtime configuration

This directory contains examples only. Real WorkerKeys stay in the user's Harness secret store, host environment, or an untracked local env file.

## MVP MCP access

The MVP assumes OpenContracts is reachable only inside a trusted LAN/VPN/restricted network domain and keeps its retrieval corpuses public inside that deployment.

Set:

```text
OPENCONTRACTS_MCP_URL=https://<internal-host>/mcp/
```

No OAuth/Bearer credential is required for normal read-side MCP access in this mode. Network reachability is the confidentiality boundary.

Future deployments may move to private corpuses and `/mcp/me/` OAuth without changing the Skill behavior.

## Upload authentication

Formal contract ingestion uses a `CorpusAccessToken` / `WorkerKey` bound to the intended history corpus.

Recommended policy:

- revoke/rotate the key when a host is retired or a key is exposed;
- use expiry/rate limits when practical;
- do not send `add_to_corpus_id` from the helper: the WorkerKey binding selects the destination;
- never place a real WorkerKey in `SKILL.md` or committed configuration.

Contract-learning material is not uploaded to OpenContracts in MVP and therefore requires no second WorkerKey.

## HTTPS

The selected MVP deployment is OpenContracts `local.yml` behind Caddy.

Caddy terminates HTTPS for the internal hostname and proxies Harness MCP/API traffic to the local Django HTTP endpoint on port 8000.

For an internal-only hostname, use Caddy `tls internal` or an organization-managed internal certificate. Every Harness host must trust the issuing CA; disabling certificate verification is not an accepted normal configuration.

Where practical, restrict raw port 8000 to loopback/host-local access so clients use Caddy rather than cleartext HTTP.
