# System Specification

## SYS-1 Runtime boundary

The Harness owns conversation/runtime state, local files, model execution and user interaction. The Skill Pack owns contract-specific behavioral guidance. OpenContracts owns retrievable enterprise contract data and formal ingestion processing.

## SYS-2 Trusted-network MVP

OpenContracts runs at a fixed private IPv4 address inside the trusted LAN/VPN. Anonymous MCP reads of public corpuses are acceptable while that network boundary remains trusted.

## SYS-3 Default contract flow

Contract-related requests activate `contract` and use local/Harness capabilities first. Database retrieval is optional and is invoked only when explicitly requested or when the assistant suggests it and the user accepts.

## SYS-4 Formal ingestion

Formal ingestion is a distinct user-authorized operation. The Harness submits the document over HTTPS without a WorkerKey; Caddy injects a server-held WorkerKey bound to `contracts-history` before forwarding to OpenContracts.

## SYS-5 Experience learning

After separate user consent, the assistant may create a local experience note. Maintainers later collect and review useful notes and update Skills through normal source-control review. No automatic learning upload, vectorized retrieval or self-modifying runtime loop is required.

## SYS-6 Deployment

The MVP deployment is OpenContracts `local.yml` behind Caddy on the same fixed LAN IP. Agent configuration uses direct `https://<fixed-lan-ip>` URLs and trusted Caddy CA certificates; there is no DNS/hosts configuration step.

## SYS-7 Future hardening

When the trusted-network assumption no longer holds, selected corpuses may move to private authenticated `/mcp/me/` access without changing the high-level Skill map.
