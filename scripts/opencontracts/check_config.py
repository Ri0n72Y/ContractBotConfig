#!/usr/bin/env python3
"""Validate OpenContracts runtime configuration without printing secrets."""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlparse


def _present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def main() -> int:
    base_url = os.getenv("OPENCONTRACTS_BASE_URL", "").strip().rstrip("/")
    mcp_url = os.getenv("OPENCONTRACTS_MCP_URL", "").strip()
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
            errors.append(f"{label} must use HTTPS in production")

    result = {
        "ok": not errors,
        "base_url_configured": bool(base_url),
        "mcp_url_configured": bool(mcp_url),
        "history_corpus_configured": _present("OPENCONTRACTS_HISTORY_CORPUS"),
        "template_corpus_configured": _present("OPENCONTRACTS_TEMPLATE_CORPUS"),
        "knowledge_corpus_configured": _present("OPENCONTRACTS_KNOWLEDGE_CORPUS"),
        "learning_corpus_configured": _present("OPENCONTRACTS_LEARNING_CORPUS"),
        "formal_upload_key_configured": _present("OPENCONTRACTS_UPLOAD_WORKER_KEY"),
        "learning_upload_key_configured": _present("OPENCONTRACTS_LEARNING_WORKER_KEY"),
        "static_mcp_bearer_configured": _present("OPENCONTRACTS_MCP_BEARER_TOKEN"),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
