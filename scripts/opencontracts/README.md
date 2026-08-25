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

The command reports only whether required settings exist. It never prints token values.

## Formal contract upload

```bash
python scripts/opencontracts/upload_document.py \
  --file /path/to/contract.docx \
  --title "设备采购合同"
```

Default credential: `OPENCONTRACTS_UPLOAD_WORKER_KEY`.

The helper sends `POST /api/imports/documents/` with `Authorization: WorkerKey ...`. It deliberately omits `add_to_corpus_id`; the server-side WorkerKey binding selects the destination corpus.

## Learning Inbox upload

```bash
python scripts/opencontracts/upload_document.py \
  --file session-facts.txt \
  --title "session facts ..." \
  --token-env OPENCONTRACTS_LEARNING_WORKER_KEY
```

Repeat for `knowledge-points.txt` only after the user has authorized learning-material ingestion.

## Write-state rule

There is no automatic HTTP retry. Network timeout, connection interruption during submission, 5xx, or an unparseable success response returns a sanitized `commit_unknown=true` result. The caller should later verify through MCP before deciding whether another upload is appropriate.
