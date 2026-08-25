# System Specification

## SYS-1 Runtime boundary

The Harness owns conversation/runtime state, local files, model execution and user interaction. The Skill Pack owns contract-specific behavior and deterministic helper usage. OpenContracts owns retrievable enterprise contract data and formal ingestion processing.

## SYS-2 Trusted-network MVP

MVP OpenContracts runs inside a trusted LAN/VPN/restricted network. Anonymous MCP reads of public corpuses are acceptable while that network boundary remains trusted.

## SYS-3 Default contract flow

Contract-related requests SHOULD activate `contract` and use local/Harness capabilities first.

Database retrieval is optional and is invoked only when explicitly requested or when the assistant suggests it and the user accepts.

## SYS-4 Formal ingestion

Formal ingestion is a distinct user-authorized operation and uses the OpenContracts upload helper with a corpus-bound WorkerKey.

## SYS-5 Experience learning

Session-learning material remains outside OpenContracts for MVP.

After separate user consent, the assistant MAY create a local experience note. The note is later collected and reviewed manually by maintainers. Skill updates occur through normal source-control/version-review workflow.

No automatic self-learning loop, Learning Inbox Corpus, vectorized retrieval or remote learning upload is required.

## SYS-6 Future hardening

When the trusted-network assumption no longer holds, OpenContracts may migrate selected corpuses to private and use authenticated `/mcp/me/` access without changing the high-level Skill map.
