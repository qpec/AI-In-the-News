"""Local presentation of an already-produced RAG result file.

This is a document viewer, not a research query, export, review or model entry
point by default. An explicit research workspace enables audited conversations.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import ipaddress
import json
from pathlib import Path
import secrets
import time
from typing import Any, cast
from urllib.parse import urlsplit

import qrcode
import qrcode.image.svg

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


def create_server(result: bytes, assets: Path, port: int = 8787, *,
                  listen: str = "127.0.0.1", pairing_key: str | None = None,
                  session_seconds: int = 7200, conversation: Any = None) -> ThreadingHTTPServer:
    """Serve one immutable in-memory document and a fixed static-file allowlist."""
    try:
        address = ipaddress.IPv4Address(listen)
    except ipaddress.AddressValueError as error:
        raise ResearchError("Choose a loopback or private IPv4 address") from error
    private_network = any(address in ipaddress.IPv4Network(network)
                          for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    if not (address.is_loopback or private_network):
        raise ResearchError("Choose a loopback or private IPv4 address")
    if not address.is_loopback and pairing_key is None:
        raise ResearchError("Phone access requires an in-memory pairing key")
    if pairing_key is not None and (not 32 <= len(pairing_key) <= 128 or not pairing_key.isascii()
                                   or not all(c.isalnum() or c in "-_" for c in pairing_key)):
        raise ResearchError("Pairing keys require 32 through 128 URL-safe ASCII characters")
    if not 1 <= session_seconds <= 86400:
        raise ResearchError("Choose a session lifetime between 1 second and 24 hours")
    expires = time.monotonic() + session_seconds
    routes = {"/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/app.css": ("app.css", "text/css; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8")}
    etag = '"' + hashlib.sha256(result).hexdigest() + '"'

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_HEAD(self) -> None:
            self._respond(head=True)

        def do_GET(self) -> None:
            self._respond()

        def _request_allowed(self, *, post: bool = False) -> bool:
            port = cast(ThreadingHTTPServer, self.server).server_port
            hosts = {f"{listen}:{port}"}
            if address.is_loopback:
                hosts.add(f"localhost:{port}")
            if port == 80:
                hosts |= {value.rsplit(":", 1)[0] for value in hosts}
            host = self.headers.get("Host", "").lower()
            origin = self.headers.get("Origin")
            return (host in hosts
                    and (not post or origin is not None)
                    and (origin is None or origin == f"http://{host}")
                    and self.headers.get("Sec-Fetch-Site") != "cross-site")

        def _authenticated(self) -> bool:
            if pairing_key is None:
                return True
            if time.monotonic() >= expires:
                return False
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
                value = cookies.get("reader_session")
                return value is not None and hmac.compare_digest(value.value.encode("utf-8"), pairing_key.encode("ascii"))
            except CookieError:
                return False

        def do_POST(self) -> None:
            if not self._request_allowed(post=True):
                self._send(403, b"Forbidden", "text/plain", False)
                return
            if self.path == "/api/conversation":
                if not self._authenticated():
                    self._send(401, b"Pairing required", "text/plain", False)
                    return
                if conversation is None:
                    self._send(404, b"Conversation mode is disabled", "text/plain", False)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 16384 or self.headers.get("Transfer-Encoding"):
                        raise ValueError("Invalid request size")
                    if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                        raise ValueError("Expected JSON")
                    data = json.loads(self.rfile.read(length))
                    response = conversation.submit(data)
                except (ValueError, ResearchError, UnicodeError, RecursionError):
                    self._send(400, b'{"error":"Invalid, conflicting or busy conversation request. Check the question, actor and authorization."}',
                        "application/json", False)
                    return
                self._send(202, json.dumps(response).encode("utf-8"), "application/json", False)
                return
            if self.path not in {"/api/pair", "/api/pair-local"} or pairing_key is None:
                self._send(404, b"Not found", "text/plain", False)
                return
            if self.path == "/api/pair-local":
                if self.client_address[0] != listen or time.monotonic() >= expires:
                    self._send(403, b"Open pairing on the host computer", "text/plain", False)
                    return
                self._finish_pairing()
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 1 <= length <= 128 or self.headers.get("Content-Type", "").split(";", 1)[0] != "text/plain":
                self._send(400, b"Invalid pairing request", "text/plain", False)
                return
            supplied = self.rfile.read(length)
            if time.monotonic() >= expires or not hmac.compare_digest(supplied, pairing_key.encode("ascii")):
                self._send(401, b"Pairing unavailable", "text/plain", False)
                return
            self._finish_pairing()

        def _finish_pairing(self) -> None:
            self._send(200, b'{"paired":true}', "application/json", False,
                cookie=f"reader_session={pairing_key}; HttpOnly; SameSite=Strict; Path=/; Max-Age={int(expires - time.monotonic())}")

        def _respond(self, head: bool = False) -> None:
            port = cast(ThreadingHTTPServer, self.server).server_port
            if not self._request_allowed():
                self._send(403, b"Forbidden", "text/plain", head)
                return
            try:
                path = urlsplit(self.path).path
            except ValueError:
                self._send(400, b"Invalid request", "text/plain", head)
                return
            if path == "/api/results":
                if not self._authenticated():
                    self._send(401, b"Scan the pairing QR on your computer", "text/plain", head)
                else:
                    self._send(200, result, "application/json; charset=utf-8", head, etag)
                return
            if path == "/api/conversation" or path.startswith("/api/conversation/jobs/"):
                if not self._authenticated():
                    self._send(401, b"Pairing required", "text/plain", head)
                    return
                if conversation is None:
                    value = {"enabled": False, "turns": []} if path == "/api/conversation" else None
                elif path == "/api/conversation":
                    value = conversation.snapshot()
                else:
                    value = conversation.job(path.removeprefix("/api/conversation/jobs/"))
                if value is None:
                    self._send(404, b"Not found", "text/plain", head)
                else:
                    self._send(200, json.dumps(value, ensure_ascii=True).encode("utf-8"), "application/json", head)
                return
            if path in {"/pairing", "/pairing.svg", "/pairing.js"}:
                if (pairing_key is None or self.client_address[0] != listen or time.monotonic() >= expires):
                    self._send(403, b"Open pairing on the host computer", "text/plain", head)
                    return
                if path == "/pairing.js":
                    script = ("document.getElementById('open-reader').addEventListener('click',async()=>{"
                        "const r=await fetch('/api/pair-local',{method:'POST',credentials:'same-origin'});"
                        "if(r.ok)location.assign('/');});")
                    self._send(200, script.encode("utf-8"), "text/javascript; charset=utf-8", head)
                elif path == "/pairing.svg":
                    pairing_url = f"http://{listen}:{port}/#pair={pairing_key}"
                    output = io.BytesIO()
                    qrcode.make(pairing_url, image_factory=qrcode.image.svg.SvgPathImage).save(output)
                    self._send(200, output.getvalue(), "image/svg+xml", head)
                else:
                    page = ("<!doctype html><html lang=en><meta name=viewport content='width=device-width,initial-scale=1'>"
                        "<link rel=stylesheet href=/app.css><script src=/pairing.js defer></script>"
                        "<title>Pair your phone</title><main class=pairing-page>"
                        "<h1>Read on your phone</h1><p>Connect your phone to the same trusted Wi-Fi as this computer. "
                        "Scan this QR code with your camera, then open the link.</p><img src=/pairing.svg "
                        "width=320 height=320 alt='Private phone pairing QR code'><p>Access expires two hours after "
                        "the server starts. Keep this computer awake and the reader running.</p>"
                        "<p>This connection stays on your local network and uses HTTP. Use your trusted home network.</p>"
                        "<button type=button id=open-reader>Open the reader on this computer</button></main></html>")
                    self._send(200, page.encode("utf-8"), "text/html; charset=utf-8", head)
                return
            if path not in routes:
                self._send(404, b"Not found", "text/plain", head)
                return
            filename, mime = routes[path]
            self._send(200, (assets / filename).read_bytes(), mime, head)

        def _send(self, status: int, content: bytes, mime: str, head: bool, tag: str | None = None,
                  cookie: str | None = None) -> None:
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
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            if not head:
                self.wfile.write(content)

    return ThreadingHTTPServer((listen, port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--listen", default="127.0.0.1", help="Specific private IPv4 address for phone access")
    parser.add_argument("--research-workspace", type=Path,
        help="Explicitly enable audited conversations using this protected store; no research occurs until submission")
    parser.add_argument("--codex-model", default="gpt-6.1-sol", help="Pinned Codex account model for authorized answers")
    parser.add_argument("--codex-executable", default="codex")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Choose a valid local port")
    result = saved_result(args.result)
    conversation = None
    if args.research_workspace is not None:
        from .conversation_controller import ConversationController

        conversation = ConversationController(args.research_workspace, json.loads(result),
            model=args.codex_model, executable=args.codex_executable)
    assets = Path(__file__).resolve().parents[2] / "web/research-review"
    pairing_key = None if ipaddress.ip_address(args.listen).is_loopback else secrets.token_urlsafe(32)
    server = create_server(result, assets, args.port, listen=args.listen, pairing_key=pairing_key,
        conversation=conversation)
    print(json.dumps({"url": f"http://{args.listen}:{server.server_port}",
        "pairing_page": f"http://{args.listen}:{server.server_port}/pairing" if pairing_key else None,
        "mode": "audited conversation reader" if conversation else "read-only saved-result viewer",
        "research_calls_at_startup": 0}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
