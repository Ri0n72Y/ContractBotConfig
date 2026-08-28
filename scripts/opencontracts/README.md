# OpenContracts helper scripts

These helpers implement deterministic conversion/write/config boundaries that should not be delegated to model-generated HTTP calls.

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

Both `convert_doc_to_pdf.py` and `upload_document.py` use `OPENCONTRACTS_CA_BUNDLE` for Python TLS verification. They do not disable certificate validation.

## Legacy `.doc` conversion

Old binary Word `.doc` files are normalized through the server-side converter before analysis or formal archive:

```bash
python scripts/opencontracts/convert_doc_to_pdf.py \
  --file /path/to/legacy-contract.doc
```

Default output:

```text
/path/to/legacy-contract.converted.pdf
```

The helper sends `POST /contract-files/convert-to-pdf` through Caddy. The internal `doc-converter` container forwards the file to the existing Gotenberg LibreOffice route on `legal-network`, validates that the result is a PDF, and returns it. The source `.doc` is never overwritten and the helper does not retry conversion requests automatically.

Only `.doc` is forced through this compatibility path. `.docx` and `.pdf` keep the normal Harness/OpenContracts flow.

## Formal contract upload

```bash
python scripts/opencontracts/upload_document.py \
  --file /path/to/contract.docx \
  --title "设备采购合同"
```

For a legacy `.doc`, convert first and upload the resulting PDF:

```bash
python scripts/opencontracts/convert_doc_to_pdf.py --file /path/to/contract.doc
python scripts/opencontracts/upload_document.py \
  --file /path/to/contract.converted.pdf \
  --title "设备采购合同"
```

Default credential: `OPENCONTRACTS_UPLOAD_WORKER_KEY`.

The upload helper sends `POST /api/imports/documents/` with `Authorization: WorkerKey ...`. It deliberately omits `add_to_corpus_id`; the server-side WorkerKey binding selects the history corpus as the destination.

Session-learning experience notes are not uploaded to OpenContracts in the MVP.

## Write-state rule

There is no automatic HTTP retry. Network timeout, connection interruption during submission, 5xx, or an unparseable success response returns a sanitized `commit_unknown=true` result. The caller should later verify through MCP before deciding whether another upload is appropriate.
