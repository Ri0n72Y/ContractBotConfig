# Specifications

This directory defines acceptance-level behavior for the portable Contract Skill Pack.

Current MVP assumptions:

- WorkBuddy/Harness owns runtime, local files and interaction;
- OpenContracts is reachable only inside a trusted LAN/VPN at a fixed private IPv4 address;
- retrieval corpuses may remain public and use anonymous `/mcp/` reads;
- Caddy provides HTTPS directly on the fixed IP in front of OpenContracts `local.yml`;
- formal contract ingestion uses a corpus-bound WorkerKey;
- session-learning material stays outside OpenContracts and is manually reviewed before Skill updates.

Files:

```text
system.md
security.md
opencontracts.md
skill-pack.md
```
