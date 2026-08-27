# OpenContracts helper scripts

These helpers implement deterministic write/config boundaries that should not be delegated to model-generated HTTP calls.

## Requirements

```bash
python -m pip install -r scripts/opencontracts/requirements.txt
```

## Validate runtime configuration

```bash
python scripts/opencontracts/check_config.py
```

The command validates the HTTPS URLs, two retrieval corpus slugs, Caddy CA bundle path, MCP-client CA setting, and formal upload WorkerKey presence. It never prints token values.

## Caddy internal CA

The MVP uses Caddy `tls internal`. Set:

```text
OPENCONTRACTS_CA_BUNDLE=<path to caddy-root.crt>
NODE_EXTRA_CA_CERTS=<same certificate path>
```

`upload_document.py` passes `OPENCONTRACTS_CA_BUNDLE` to the Python `requests` TLS verifier. It does not disable certificate validation.

## Formal contract upload

```bash
python scripts/opencontracts/upload_document.py \
  --file /path/to/contract.docx \
  --title "设备采购合同"
```

Default credential: `OPENCONTRACTS_UPLOAD_WORKER_KEY`.

The helper sends `POST /api/imports/documents/` with `Authorization: WorkerKey ...`. It deliberately omits `add_to_corpus_id`; the server-side WorkerKey binding selects `contracts-history` as the destination.

Session-learning experience notes are not uploaded to OpenContracts in the MVP.

## Write-state rule

There is no automatic HTTP retry. Network timeout, connection interruption during submission, 5xx, or an unparseable success response returns a sanitized `commit_unknown=true` result. The caller should later verify through MCP before deciding whether another upload is appropriate.
