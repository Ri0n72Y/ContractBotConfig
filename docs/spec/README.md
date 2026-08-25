# Specifications

This directory defines the acceptance-level behavior for the portable Contract Skill Pack.

Current MVP assumptions:

- WorkBuddy/Harness owns runtime, local files and interaction;
- OpenContracts is reachable only inside a trusted network;
- OpenContracts retrieval corpuses may remain public and use anonymous `/mcp/` reads;
- formal contract ingestion uses a corpus-bound WorkerKey;
- session-learning material stays outside OpenContracts and is manually reviewed before Skill updates;
- HTTPS is required for the intended deployment path, using bundled production Traefik or an internal reverse proxy such as Caddy.

Files:

```text
system.md
security.md
opencontracts.md
skill-pack.md
```
