from __future__ import annotations

import hashlib
import os
import socket
import tempfile
from pathlib import Path

import httpx
from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

PDF_MAGIC = b"%PDF"
GOTENBERG_URL = os.getenv(
    "GOTENBERG_URL",
    "http://gotenberg:3000/forms/libreoffice/convert",
).strip()
REQUEST_TIMEOUT_SECONDS = float(os.getenv("CONVERTER_TIMEOUT_SECONDS", "90"))
MAX_FILE_BYTES = int(os.getenv("CONVERTER_MAX_FILE_BYTES", str(100 * 1024 * 1024)))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_BYTES + (1024 * 1024)


class DocConversionError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _error(code: str, status: int):
    return jsonify(ok=False, error=code), status


def _safe_pdf_name(original_name: str) -> str:
    source = Path(original_name or "contract.doc").name
    stem = source[: -len(Path(source).suffix)] or "contract"
    return f"{stem}.pdf"


def _connect_error_code(exc: httpx.ConnectError) -> str:
    current: BaseException | None = exc
    for _ in range(8):
        current = getattr(current, "__cause__", None)
        if current is None:
            break
        if isinstance(current, socket.gaierror):
            return "converter_dns_failed"
        if isinstance(current, ConnectionRefusedError):
            return "converter_connection_refused"
        if isinstance(current, (socket.timeout, TimeoutError)):
            return "converter_timeout"
    return "converter_unreachable"


def _convert(uploaded, original_name: str) -> tuple[bytes, str, str]:
    if not GOTENBERG_URL:
        raise DocConversionError("converter_url_missing")

    source_digest = hashlib.sha256()
    source_size = 0

    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as source:
        while True:
            block = uploaded.stream.read(1024 * 1024)
            if not block:
                break
            source_size += len(block)
            if source_size > MAX_FILE_BYTES:
                raise DocConversionError("source_size_invalid")
            source_digest.update(block)
            source.write(block)

        if source_size <= 0:
            raise DocConversionError("source_size_invalid")

        source.seek(0)
        timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(
                    GOTENBERG_URL,
                    headers={"Accept": "application/pdf"},
                    files={
                        "files": (
                            Path(original_name).name,
                            source,
                            "application/msword",
                        )
                    },
                )
        except httpx.TimeoutException as exc:
            raise DocConversionError("converter_timeout") from exc
        except httpx.ConnectError as exc:
            raise DocConversionError(_connect_error_code(exc)) from exc
        except httpx.RequestError as exc:
            raise DocConversionError("converter_request_error") from exc

    if response.status_code >= 400:
        raise DocConversionError(f"converter_http_{response.status_code}")

    result = response.content
    if len(result) > MAX_FILE_BYTES:
        raise DocConversionError("converted_file_too_large")
    if not result.startswith(PDF_MAGIC):
        raise DocConversionError("converter_returned_non_pdf")

    return result, source_digest.hexdigest(), hashlib.sha256(result).hexdigest()


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_exc):
    return _error("source_size_invalid", 413)


@app.post("/contract-files/convert-to-pdf")
def convert_doc_to_pdf():
    uploaded = request.files.get("file")
    if uploaded is None:
        return _error("source_file_missing", 400)

    original_name = Path(uploaded.filename or "contract.doc").name
    if Path(original_name).suffix.lower() != ".doc":
        return _error("source_format_unsupported", 415)

    try:
        pdf_bytes, source_sha256, output_sha256 = _convert(uploaded, original_name)
    except DocConversionError as exc:
        status = 504 if exc.code == "converter_timeout" else 502
        if exc.code == "source_size_invalid":
            status = 413
        app.logger.warning("DOC conversion failed code=%s", exc.code)
        return _error(exc.code, status)

    app.logger.info(
        "DOC conversion complete source_sha256=%s output_sha256=%s output_name=%s",
        source_sha256,
        output_sha256,
        _safe_pdf_name(original_name),
    )
    response = Response(pdf_bytes, status=200, mimetype="application/pdf")
    response.headers["Content-Disposition"] = 'attachment; filename="converted.pdf"'
    response.headers["X-Source-SHA256"] = source_sha256
    response.headers["X-Output-SHA256"] = output_sha256
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
