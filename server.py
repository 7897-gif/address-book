"""A small HTTP server for the address book, built on the Python standard library.

Only one third-party package is required: openpyxl (for .xlsx import/export).
Everything else — routing, JSON handling, static files, multipart uploads —
comes from the standard library so the project runs anywhere Python 3.9+ does.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import traceback
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from excel_io import (
    ImportError_,
    export_workbook,
    read_import_file,
    template_workbook,
)
from repository import AddressBook, ValidationError

MAX_BODY_BYTES = 8 * 1024 * 1024

ROUTE_CONTACT = re.compile(r"^/api/contacts/(\d+)$")
ROUTE_FAVORITE = re.compile(r"^/api/contacts/(\d+)/favorite$")


class AddressBookServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, book: AddressBook, static_dir: Path):
        super().__init__(address, AppHandler)
        self.book = book
        self.static_dir = Path(static_dir)


class AppHandler(BaseHTTPRequestHandler):
    server: AddressBookServer
    server_version = "AddressBook/1.0"
    protocol_version = "HTTP/1.1"

    # ----------------------------------------------------------------- http
    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                self._api(method, path, query)
            elif method == "GET":
                self._static(path)
            else:
                self._json({"error": "Method not allowed."}, status=405)
        except BrokenPipeError:  # the browser navigated away mid-response
            pass
        except ValidationError as exc:
            self._json_error("Validation failed.", 400, {"errors": exc.errors})
        except ImportError_ as exc:
            self._json_error(str(exc), 400)
        except ValueError as exc:
            self._json_error(str(exc), 400)
        except Exception:
            traceback.print_exc()
            self._json({"error": "Internal server error."}, status=500)

    # ------------------------------------------------------------------ api
    def _api(self, method: str, path: str, query: dict) -> None:
        book = self.server.book

        if path == "/api/contacts":
            if method == "GET":
                search = (query.get("q") or [""])[0]
                only_favorites = (query.get("favorite") or [""])[0] in {"1", "true", "yes"}
                items = book.list_contacts(search, only_favorites)
                return self._json({"items": items, "stats": book.stats()})
            if method == "POST":
                payload = self._body_json()
                contact = book.create_contact(payload)
                return self._json({"contact": contact}, status=201)

        if path == "/api/stats" and method == "GET":
            return self._json(book.stats())

        match = ROUTE_CONTACT.match(path)
        if match:
            contact_id = int(match.group(1))
            if method == "GET":
                contact = book.get_contact(contact_id)
                if contact is None:
                    return self._json({"error": "Contact not found."}, status=404)
                return self._json({"contact": contact})
            if method in {"PUT", "PATCH"}:
                contact = book.update_contact(contact_id, self._body_json())
                if contact is None:
                    return self._json({"error": "Contact not found."}, status=404)
                return self._json({"contact": contact})
            if method == "DELETE":
                if not book.delete_contact(contact_id):
                    return self._json({"error": "Contact not found."}, status=404)
                return self._json({"deleted": contact_id})

        match = ROUTE_FAVORITE.match(path)
        if match and method == "POST":
            payload = self._body_json()
            contact = book.set_favorite(int(match.group(1)), payload.get("favorite"))
            if contact is None:
                return self._json({"error": "Contact not found."}, status=404)
            return self._json({"contact": contact})

        if path == "/api/export" and method == "GET":
            data = export_workbook(book.list_contacts())
            return self._download(
                data,
                "address-book.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if path == "/api/template" and method == "GET":
            return self._download(
                template_workbook(),
                "address-book-template.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if path == "/api/import" and method == "POST":
            data, _filename = self._upload()
            summary, created = read_import_file(book, data)
            summary["items"] = created
            return self._json(summary)

        return self._json({"error": f"No route for {method} {path}."}, status=404)

    # --------------------------------------------------------------- helpers
    def _body_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("Request body too large.")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _upload(self) -> tuple[bytes, str]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ImportError_("No file was uploaded.")
        if length > MAX_BODY_BYTES:
            raise ImportError_("The upload is too large.")
        raw = self.rfile.read(length)

        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            message = BytesParser(policy=policy.default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
                + raw
            )
            for part in message.iter_parts():
                if part.get_filename():
                    return part.get_payload(decode=True) or b"", part.get_filename()
            raise ImportError_("No file was found in the multipart body.")

        filename = self.headers.get("X-Filename") or "upload.xlsx"
        return raw, filename

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _download(self, data: bytes, filename: str, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        target = (self.server.static_dir / path.lstrip("/")).resolve()
        root = self.server.static_dir.resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            return self._json({"error": "Not found."}, status=404)
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ---------------------------------------------------------------- errors
    def _json_error(self, message: str, status: int, extra: dict | None = None) -> None:
        payload = {"error": message}
        if extra:
            payload.update(extra)
        self._json(payload, status=status)

    def send_error(self, code, message=None, explain=None):  # pragma: no cover
        # Only used for malformed HTTP requests, not for application errors.
        super().send_error(code, message, explain)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")


def create_server(host: str, port: int, db_path: str, static_dir: Path) -> AddressBookServer:
    book = AddressBook(db_path)
    return AddressBookServer((host, port), book, static_dir)
