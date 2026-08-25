# OpenContracts runtime configuration

This directory contains examples only. Real secrets stay in the user's Harness secret store, host environment, or an untracked local env file.

## Preferred MCP authentication

Set:

```text
OPENCONTRACTS_MCP_URL=https://<host>/mcp/me/
```

and let a capable Harness complete OpenContracts OAuth. This keeps the read identity per-user and avoids distributing one shared long-lived read token inside the Skill Pack.

If a Harness cannot perform OAuth, a separately provisioned Bearer token may be configured by the runtime. Do not place it in `SKILL.md`, `.mcp.json`, committed JSON, examples, logs, or generated reports.

## Upload authentication

Formal contract ingestion uses a `CorpusAccessToken` / `WorkerKey` bound to the intended history corpus. Learning uploads use a second WorkerKey bound to `learning-inbox`.

Recommended operational policy:

- one tenant per identity/corpus set;
- preferably one WorkerKey per user/device/host and per destination corpus;
- set expiry and rate limits;
- revoke a leaked or retired key immediately;
- never reuse a Learning Inbox key for formal contract ingestion;
- do not send `add_to_corpus_id` from the helper: the WorkerKey binding selects the destination.

## Corpus isolation

OpenContracts MCP corpus-scoped reads intentionally use Corpus READ as the gate. Therefore confidential groups must be separated into different private corpuses. Do not place restricted documents inside a generally readable corpus and expect document-level ACLs to hide them from MCP.
