#!/usr/bin/env python3
"""Validate OpenContracts runtime configuration without printing secrets."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


def _present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def main() -> int:
    base_url = os.getenv("OPENCONTRACTS_BASE_URL", "").strip().rstrip("/")
    mcp_url = os.getenv("OPENCONTRACTS_MCP_URL", "").strip()
    ca_bundle = os.getenv("OPENCONTRACTS_CA_BUNDLE", "").strip()
    allow_insecure = os.getenv("OPENCONTRACTS_ALLOW_INSECURE_HTTP", "0") == "1"

    errors: list[str] = []
    for label, value in (
        ("OPENCONTRACTS_BASE_URL", base_url),
        ("OPENCONTRACTS_MCP_URL", mcp_url),
    ):
        if not value:
            errors.append(f"{label} is missing")
            continue
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            errors.append(f"{label} is not a valid HTTP(S) URL")
        elif parsed.scheme != "https" and not allow_insecure:
            errors.append(f"{label} must use HTTPS in the MVP deployment")

    if not _present("OPENCONTRACTS_HISTORY_CORPUS"):
        errors.append("OPENCONTRACTS_HISTORY_CORPUS is missing")
    if not _present("OPENCONTRACTS_TEMPLATE_CORPUS"):
        errors.append("OPENCONTRACTS_TEMPLATE_CORPUS is missing")
    if not _present("OPENCONTRACTS_KNOWLEDGE_CORPUS"):
        errors.append("OPENCONTRACTS_KNOWLEDGE_CORPUS is missing")

    ca_exists = False
    if ca_bundle:
        ca_exists = Path(ca_bundle).expanduser().is_file()
        if not ca_exists:
            errors.append("OPENCONTRACTS_CA_BUNDLE does not point to a file")
    else:
        errors.append("OPENCONTRACTS_CA_BUNDLE is missing")

    result = {
        "ok": not errors,
        "base_url_configured": bool(base_url),
        "mcp_url_configured": bool(mcp_url),
        "history_corpus_configured": _present("OPENCONTRACTS_HISTORY_CORPUS"),
        "template_corpus_configured": _present("OPENCONTRACTS_TEMPLATE_CORPUS"),
        "knowledge_corpus_configured": _present("OPENCONTRACTS_KNOWLEDGE_CORPUS"),
        "ca_bundle_configured": bool(ca_bundle),
        "ca_bundle_exists": ca_exists,
        "node_extra_ca_configured": _present("NODE_EXTRA_CA_CERTS"),
        "formal_upload_key_configured": _present("OPENCONTRACTS_UPLOAD_WORKER_KEY"),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
