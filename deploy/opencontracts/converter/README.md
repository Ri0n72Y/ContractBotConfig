# Optional legacy DOC converter

This directory keeps the lightweight `.doc` → PDF adapter extracted from the former AstrBot preconverter.

It is **not part of the default OpenContracts/Caddy deployment**.

Default behavior is local-first: the Harness should first use local Word/Office/document capabilities. Deploy this container only when a centralized fallback is needed.

## What it does

`app.py` accepts a legacy `.doc`, forwards it to the existing Gotenberg LibreOffice route on `legal-network`, verifies `%PDF`, and returns the PDF.

It does not use an LLM, does not perform OCR, does not write to OpenContracts, and does not keep long-term document copies.

## Optional deployment

The compose file only joins the existing `legal-network`:

```powershell
cd deploy/opencontracts/converter
.\manage.ps1 up
```

The service is available as:

```text
doc-converter:8080
```

inside `legal-network`.

There is deliberately:

- no `ports:` mapping;
- no default Caddy route;
- no LAN-accessible conversion endpoint.

So deploying this optional container alone does not expose the conversion capability.

## Future exposure

If a deployment later decides to make the fallback available to Harness clients, add an explicit Caddy route and configure the client with:

```text
OPENCONTRACTS_CONVERTER_URL=https://<server>/contract-files/convert-to-pdf
```

The existing `scripts/opencontracts/convert_doc_to_pdf.py` can then call that endpoint.

## Runtime defaults

```text
GOTENBERG_URL=http://gotenberg:3000/forms/libreoffice/convert
CONVERTER_TIMEOUT_SECONDS=90
CONVERTER_MAX_FILE_BYTES=104857600
```

The implementation retains the useful boundaries from the old AstrBot converter: `.doc` only, bounded size, safe error codes, SHA-256 metadata, and PDF magic validation.
