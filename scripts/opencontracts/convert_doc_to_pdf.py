#!/usr/bin/env python3
"""Convert one legacy .doc file through an explicitly enabled remote endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

PDF_MAGIC = b"%PDF"


def emit(**payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        emit(ok=False, status="failed", error="file_not_found")
        return 2
    if source.suffix.lower() != ".doc":
        emit(ok=False, status="blocked", error="source_format_unsupported")
        return 2

    endpoint = os.getenv("OPENCONTRACTS_CONVERTER_URL", "").strip()
    ca_bundle = os.getenv("OPENCONTRACTS_CA_BUNDLE", "").strip()
    allow_insecure = os.getenv("OPENCONTRACTS_ALLOW_INSECURE_HTTP", "0") == "1"
    try:
        timeout = max(
            1.0,
            float(os.getenv("OPENCONTRACTS_CONVERT_TIMEOUT_SECONDS", "120")),
        )
    except ValueError:
        timeout = 120.0

    if not endpoint:
        emit(ok=False, status="blocked", error="converter_not_enabled")
        return 2

    parsed = urlparse(endpoint)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        emit(ok=False, status="blocked", error="invalid_converter_url")
        return 2
    if parsed.scheme != "https" and not allow_insecure:
        emit(ok=False, status="blocked", error="https_required")
        return 2

    verify: bool | str = True
    if ca_bundle:
        ca_path = Path(ca_bundle).expanduser().resolve()
        if not ca_path.is_file():
            emit(ok=False, status="blocked", error="ca_bundle_not_found")
            return 2
        verify = str(ca_path)

    output = (
        Path(args.output).expanduser().resolve()
        if args.output.strip()
        else source.with_name(f"{source.stem}.converted.pdf")
    )
    if output == source:
        emit(ok=False, status="blocked", error="output_matches_source")
        return 2
    if output.exists():
        emit(ok=False, status="blocked", error="output_exists", output_path=str(output))
        return 2

    try:
        with source.open("rb") as handle:
            with requests.Session() as session:
                session.trust_env = False
                response = session.post(
                    endpoint,
                    headers={"Accept": "application/pdf"},
                    files={"file": (source.name, handle, "application/msword")},
                    timeout=timeout,
                    verify=verify,
                )
    except requests.RequestException:
        emit(ok=False, status="failed", error="converter_request_error")
        return 3

    if response.status_code >= 400:
        error_code = "converter_failed"
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("error"), str):
                error_code = payload["error"]
        except ValueError:
            pass
        emit(ok=False, status="failed", http_status=response.status_code, error=error_code)
        return 3

    pdf_bytes = response.content
    if not pdf_bytes.startswith(PDF_MAGIC):
        emit(ok=False, status="failed", error="converter_returned_non_pdf")
        return 3

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        temporary.write_bytes(pdf_bytes)
        temporary.replace(output)
    except OSError:
        try:
            if temporary.is_file():
                temporary.unlink()
        except OSError:
            pass
        emit(ok=False, status="failed", error="converted_file_write_failed")
        return 3

    emit(
        ok=True,
        status="converted",
        source_sha256=response.headers.get("X-Source-SHA256"),
        output_sha256=response.headers.get("X-Output-SHA256") or sha256_bytes(pdf_bytes),
        output_path=str(output),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
