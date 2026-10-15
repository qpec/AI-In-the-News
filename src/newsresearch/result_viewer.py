"""Read-only local presentation of an already-produced RAG result file.

This is a document viewer, not a research query, export, review or model entry
point. It never opens the research database or modifies an assessment.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from .common import ResearchError
from .storage import check_permissions


def saved_result(path: Path) -> bytes:
    path = path.expanduser().absolute()
    for current in (path, *path.parents):
        if current.is_symlink() or current.is_junction() or (current / ".git").exists():
            raise ResearchError("The saved result must stay in protected storage outside Git")
    check_permissions(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ResearchError("The saved result is too large for this document viewer")
    content = path.read_bytes()
    value: Any = json.loads(content)
    if (not isinstance(value, dict) or not isinstance(value.get("id"), str)
            or not isinstance(value.get("rows"), list) or not isinstance(value.get("question"), str)):
        raise ResearchError("Choose an existing RAG result JSON file")
    return content


def create_server(result: bytes, assets: Path, port: int = 8787) -> ThreadingHTTPServer:
    """Serve one immutable in-memory document and a fixed static-file allowlist."""
    routes = {"/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/app.css": ("app.css", "text/css; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8")}
    etag = '"' + hashlib.sha256(result).hexdigest() + '"'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_HEAD(self) -> None:
            self._respond(head=True)

        def do_GET(self) -> None:
            self._respond()

        def _respond(self, head: bool = False) -> None:
            port = cast(ThreadingHTTPServer, self.server).server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if port == 80:
                hosts |= {"127.0.0.1", "localhost"}
            host = self.headers.get("Host", "").lower()
            origin = self.headers.get("Origin")
            if host not in hosts or (origin is not None and origin not in {f"http://{h}" for h in hosts}):
                self._send(403, b"Forbidden", "text/plain", head)
                return
            try:
                path = urlsplit(self.path).path
            except ValueError:
                self._send(400, b"Invalid request", "text/plain", head)
                return
            if path == "/api/results":
                if self.headers.get("Sec-Fetch-Site") == "cross-site":
                    self._send(403, b"Forbidden", "text/plain", head)
                else:
                    self._send(200, result, "application/json; charset=utf-8", head, etag)
                return
            if path not in routes:
                self._send(404, b"Not found", "text/plain", head)
                return
            filename, mime = routes[path]
            self._send(200, (assets / filename).read_bytes(), mime, head)

        def _send(self, status: int, content: bytes, mime: str, head: bool, tag: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                "object-src 'none'; form-action 'none'")
            if tag:
                self.send_header("ETag", tag)
            self.end_headers()
            if not head:
                self.wfile.write(content)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Choose a valid local port")
    result = saved_result(args.result)
    assets = Path(__file__).resolve().parents[2] / "web/research-review"
    server = create_server(result, assets, args.port)
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}",
        "mode": "read-only saved-result viewer", "research_calls": 0}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
