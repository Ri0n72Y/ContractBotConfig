# Contract database analysis P0-P1

## Scope

This change fixes deterministic OpenContracts database reads and long WeCom text delivery.

## P0

- Master database-read requests expose only `transfer_to_opencontracts_operator`.
- OpenContracts Operator MCP toolsets are not stripped by the Master restriction.
- Read-only handoffs use `list_documents`, `get_document_text`, and `search_corpus` only.
- Document text is read from offset zero until `next_offset` is null.
- Empty text, `page_count=0`, or `total_chars=0` returns `CONTRACT_READ:PENDING` without local fallback.
- `READY`, `PARTIAL`, `PENDING`, and `FAILED` are terminal read states.

## P1

- Handoff sends one immediate processing acknowledgement before database analysis.
- Result Guard splits long UTF-8 text at natural paragraph boundaries.
- Intermediate segments are sent as real WeCom messages; the final segment remains in the normal result chain.
- The previous unsupported attachment promise is removed.

## Validation

- Python compilation completed for the changed plugin modules.
- JSON parsing completed for configuration schemas and Persona files.
- Simulated tool filtering confirmed that Master Shell/Grep/Python tools are removed while Operator MCP tools remain available.
- Simulated handoff confirmed read-only canonical tools and one acknowledgement per event.
- Simulated Result Guard delivery confirmed all text segments remain within the configured byte limit.

Temporary HTML/Markdown reports and Nginx publication remain outside this P0-P1 scope.
