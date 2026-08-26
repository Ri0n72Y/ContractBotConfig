#!/usr/bin/env python3
"""Upload one document to OpenContracts with a corpus-bound WorkerKey.

No automatic retries are performed. Secrets are read directly from the process
environment and are never included in output.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


def emit(**payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--folder", default="")
    parser.add_argument(
        "--token-env",
        default="OPENCONTRACTS_UPLOAD_WORKER_KEY",
        help="Environment variable containing the corpus-bound WorkerKey",
    )
    args = parser.parse_args()

    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        emit(ok=False, status="failed", retry_safe=True, error="file_not_found")
        return 2

    base_url = os.getenv("OPENCONTRACTS_BASE_URL", "").strip().rstrip("/")
    token = os.getenv(args.token_env, "").strip()
    ca_bundle = os.getenv("OPENCONTRACTS_CA_BUNDLE", "").strip()
    allow_insecure = os.getenv("OPENCONTRACTS_ALLOW_INSECURE_HTTP", "0") == "1"
    try:
        timeout = max(1.0, float(os.getenv("OPENCONTRACTS_UPLOAD_TIMEOUT_SECONDS", "60")))
    except ValueError:
        timeout = 60.0

    if not base_url or not token:
        emit(
            ok=False,
            status="blocked",
            retry_safe=True,
            error="missing_runtime_configuration",
            token_env=args.token_env,
        )
        return 2

    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        emit(ok=False, status="blocked", retry_safe=True, error="invalid_base_url")
        return 2
    if parsed.scheme != "https" and not allow_insecure:
        emit(ok=False, status="blocked", retry_safe=True, error="https_required")
        return 2

    verify: bool | str = True
    if ca_bundle:
        ca_path = Path(ca_bundle).expanduser().resolve()
        if not ca_path.is_file():
            emit(ok=False, status="blocked", retry_safe=True, error="ca_bundle_not_found")
            return 2
        verify = str(ca_path)

    endpoint = f"{base_url}/api/imports/documents/"
    mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    data: dict[str, str] = {
        "filename": source.name,
        "title": args.title.strip(),
        "description": args.description.strip(),
    }
    if args.folder.strip():
        data["add_to_folder_path"] = args.folder.strip().strip("/")

    headers = {"Authorization": f"WorkerKey {token}"}

    try:
        with source.open("rb") as handle:
            response = requests.post(
                endpoint,
                headers=headers,
                files={"file": (source.name, handle, mime)},
                data=data,
                timeout=timeout,
                verify=verify,
            )
    except requests.RequestException:
        emit(
            ok=False,
            status="commit_unknown",
            commit_unknown=True,
            retry_safe=False,
            error="transport_or_timeout",
        )
        return 3

    if 200 <= response.status_code < 300:
        try:
            body = response.json()
        except ValueError:
            emit(
                ok=False,
                status="commit_unknown",
                commit_unknown=True,
                retry_safe=False,
                http_status=response.status_code,
                error="unparseable_success_response",
            )
            return 3

        # A successful import response only proves submission/acceptance.
        emit(
            ok=True,
            status="submitted",
            processing=True,
            searchable=False,
            retry_safe=False,
            http_status=response.status_code,
            document_id=body.get("document_id") or body.get("id"),
            job_id=body.get("job_id"),
        )
        return 0

    if response.status_code >= 500:
        emit(
            ok=False,
            status="commit_unknown",
            commit_unknown=True,
            retry_safe=False,
            http_status=response.status_code,
            error="upstream_server_error",
        )
        return 3

    # A normal 4xx rejection is treated as a known failure. Do not echo the
    # response body: it can contain deployment details that should stay local.
    emit(
        ok=False,
        status="failed",
        commit_unknown=False,
        retry_safe=True,
        http_status=response.status_code,
        error="request_rejected",
    )
    return 4


if __name__ == "__main__":
    sys.exit(main())
