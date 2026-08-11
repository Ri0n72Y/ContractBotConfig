#!/usr/bin/env python3
"""Upload the ContractBot smoke interview to a Docassemble Playground.

The API key is read only from DOCASSEMBLE_API_KEY. The script never prints it.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_FILE = Path("docs/docassemble/contractbot_api_smoke.yml")


def request_json(
    url: str,
    api_key: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str | None = None,
) -> Any:
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "User-Agent": "ContractBot-Docassemble-Smoke-Deployer/0.1",
    }
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Docassemble did not return JSON") from exc


def multipart_file(
    field_name: str,
    file_path: Path,
    fields: dict[str, str],
) -> tuple[bytes, str]:
    boundary = f"contractbot-{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                ).encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                "Content-Disposition: form-data; "
                f'name="{field_name}"; filename="{file_path.name}"\r\n'
            ).encode(),
            b"Content-Type: application/x-yaml\r\n\r\n",
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def interview_name(user_id: int, project: str, filename: str) -> str:
    if project == "default":
        package = f"docassemble.playground{user_id}"
    else:
        if not project.isalnum() or project[0].isdigit():
            raise ValueError(
                "project must be alphanumeric and must not begin with a digit"
            )
        package = f"docassemble.playground{user_id}{project}"
    return f"{package}:{filename}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "DOCASSEMBLE_BASE_URL",
            "http://localhost:8080",
        ),
    )
    parser.add_argument("--project", default="default")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    args = parser.parse_args()

    api_key = os.environ.get("DOCASSEMBLE_API_KEY", "").strip()
    if not api_key:
        print(
            "DOCASSEMBLE_API_KEY is not set; refusing to accept the key on the command line.",
            file=sys.stderr,
        )
        return 2
    if not args.file.is_file():
        print(f"smoke interview not found: {args.file}", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    try:
        user = request_json(f"{base_url}/api/user", api_key)
        user_id = int(user["id"])

        body, content_type = multipart_file(
            "file",
            args.file,
            {
                "folder": "questions",
                "project": args.project,
                "restart": "0",
            },
        )
        request_json(
            f"{base_url}/api/playground",
            api_key,
            method="POST",
            data=body,
            content_type=content_type,
        )

        full_name = interview_name(user_id, args.project, args.file.name)
        query = urllib.parse.urlencode({"i": full_name})
        inspected = request_json(
            f"{base_url}/api/interview_data?{query}",
            api_key,
        )
        if not isinstance(inspected, dict) or "names" not in inspected:
            raise RuntimeError("interview_data validation returned an unexpected body")
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"Docassemble smoke deployment failed: {exc}", file=sys.stderr)
        return 1

    print("Docassemble smoke interview deployed and validated.")
    print(f"interview={full_name}")
    print(f"gateway_base_url=http://docassemble")
    print("Set this exact interview value in allowed_interviews/default_interview.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
