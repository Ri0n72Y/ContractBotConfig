# OpenContracts client helpers

These deterministic helpers are installed under `CONTRACTBOT_HOME/scripts/opencontracts/`. Skills must not depend on the user's current project directory.

The Windows fallback installer places the runtime under `%LOCALAPPDATA%\ContractBot` and installs `requests` for the current user when a normal Python launcher is available.

## Formal upload

Use `CONTRACTBOT_HOME/scripts/opencontracts/upload_document.py`. It reads `OPENCONTRACTS_UPLOAD_WORKER_KEY`, sends the corpus-bound WorkerKey to `/api/imports/documents/`, never accepts a caller-selected destination Corpus, and never automatically retries an ambiguous write.

## Configuration check

`check_config.py` validates the client runtime without printing secrets.

## Legacy `.doc`

`convert_doc_to_pdf.py` is only an optional remote fallback. Local Harness/Office conversion remains preferred and the helper stays blocked unless `OPENCONTRACTS_CONVERTER_URL` is explicitly configured.
