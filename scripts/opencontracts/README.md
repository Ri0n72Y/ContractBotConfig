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

`upload_document.py` uses `OPENCONTRACTS_CA_BUNDLE` for Python TLS verification. It does not disable certificate validation.

## Legacy `.doc` handling

The default contract Skills are local-first:

1. Let the Harness use its native local document capability first. On many Windows hosts this can reuse an installed Word/Office stack.
2. If the Harness can reliably read the document, analysis can proceed directly without producing a PDF.
3. If formal OpenContracts ingestion needs a compatible file, prefer a locally generated PDF working copy.
4. The optional server-side converter is only a fallback for deployments that explicitly enable and expose it.

The repository keeps `convert_doc_to_pdf.py` for that optional fallback. It is not part of the default deployment and should not be called merely because the script exists.

When an operator later exposes an approved converter endpoint, set the full endpoint explicitly:

```text
OPENCONTRACTS_CONVERTER_URL=https://<server>/contract-files/convert-to-pdf
```

Then the helper can be used:

```bash
python scripts/opencontracts/convert_doc_to_pdf.py \
  --file /path/to/legacy-contract.doc
```

The source `.doc` is never overwritten.

## Formal contract upload

```bash
python scripts/opencontracts/upload_document.py \
  --file /path/to/contract.docx \
  --title "设备采购合同"
```

For legacy `.doc`, upload a reliable PDF working copy produced by the Harness or, when explicitly enabled, by the optional converter.

Default credential: `OPENCONTRACTS_UPLOAD_WORKER_KEY`.

The upload helper sends `POST /api/imports/documents/` with `Authorization: WorkerKey ...`. It deliberately omits `add_to_corpus_id`; the server-side WorkerKey binding selects the history corpus as the destination.

Session-learning experience notes are not uploaded to OpenContracts in the MVP.

## Write-state rule

There is no automatic HTTP retry. Network timeout, connection interruption during submission, 5xx, or an unparseable success response returns a sanitized `commit_unknown=true` result. The caller should later verify through MCP before deciding whether another upload is appropriate.
