"""Synthetic local HTTP checks for optional private-network document access."""

from __future__ import annotations

import http.client
from http.cookies import SimpleCookie
import threading
from typing import Any

import pytest

from newsresearch.common import ResearchError
from newsresearch.result_viewer import create_server


KEY = "synthetic-mobile-pairing-session-" + "x" * 40


@pytest.fixture
def mobile_factory(tmp_path: Any):
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ("index.html", "app.js", "app.css"):
        (assets / name).write_text("Synthetic public asset", encoding="utf-8")
    document = b'{"id":"synthetic-mobile", "question":"Synthetic question", "rows":[]}'
    started = []

    def factory(**kwargs: Any):
        server = create_server(document, assets, 0, **kwargs)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread))
        return server, document

    yield factory
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join()


def request(server: Any, path: str = "/api/results", *, method: str = "GET",
            headers: dict[str, str] | None = None, body: Any = None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def origin(server: Any) -> str:
    return f"http://127.0.0.1:{server.server_port}"


def pair(server: Any, key: str = KEY, **kwargs: Any):
    headers = {"Origin": origin(server), "Content-Type": "text/plain", **kwargs.pop("headers", {})}
    return request(server, "/api/pair", method="POST", headers=headers,
                   body=key, **kwargs)


@pytest.mark.parametrize("listen", ["0.0.0.0", "8.8.8.8", "::", "::1", "localhost", "example.com",
                                    "224.0.0.1", "255.255.255.255", "not-an-address", "169.254.1.2",
                                    "198.51.100.1"])
def test_unsafe_or_ambiguous_listen_addresses_are_rejected(mobile_factory: Any, listen: str) -> None:
    with pytest.raises(ResearchError):
        mobile_factory(listen=listen, pairing_key=KEY)


def test_private_network_listen_requires_a_session_key_before_binding(mobile_factory: Any) -> None:
    with pytest.raises(ResearchError, match="[Kk]ey|pair|session"):
        mobile_factory(listen="192.168.1.23")


@pytest.mark.parametrize("key", ["", "short", "x" * 31, "a" * 31 + "é", "a" * 31 + "/"])
def test_weak_or_non_url_safe_pairing_keys_are_rejected(mobile_factory: Any, key: str) -> None:
    with pytest.raises(ResearchError, match="[Kk]ey|pair|ASCII"):
        mobile_factory(listen="127.0.0.1", pairing_key=key)


def test_authenticated_mode_never_serves_data_before_pairing(mobile_factory: Any) -> None:
    server, document = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    for method in ("GET", "HEAD"):
        status, headers, body = request(server, method=method)
        assert status == 401
        assert document not in body
        assert headers["Cache-Control"] == "no-store"
    assert request(server, "/")[0] == 200
    assert request(server, "/app.js")[0] == 200
    assert request(server, f"/api/results?key={KEY}")[0] == 401


def test_pairing_sets_private_cookie_and_serves_exact_immutable_document(mobile_factory: Any) -> None:
    server, document = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    status, headers, body = pair(server)
    assert status in {200, 204} and KEY.encode() not in body
    cookie = SimpleCookie()
    cookie.load(headers["Set-Cookie"])
    assert len(cookie) == 1
    morsel = next(iter(cookie.values()))
    assert morsel["httponly"] and morsel["samesite"].lower() == "strict"
    assert morsel["path"] == "/" and int(morsel["max-age"]) <= 7200
    authenticated = {"Cookie": f"{morsel.key}={morsel.value}"}
    status, headers, body = request(server, headers=authenticated)
    assert status == 200 and body == document
    assert headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers
    assert request(server, headers=authenticated, method="HEAD")[2] == b""


@pytest.mark.parametrize("extra", [
    {"Host": "malicious.test"}, {"Origin": "https://malicious.test"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_pairing_rejects_cross_site_and_rebinding_headers(mobile_factory: Any, extra: dict[str, str]) -> None:
    server, _ = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    status, headers, _ = pair(server, headers=extra)
    assert status == 403 and "Set-Cookie" not in headers


def test_invalid_keys_and_malformed_json_never_issue_a_cookie(mobile_factory: Any) -> None:
    server, _ = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    status, headers, body = pair(server, "wrong-key")
    assert status in {400, 401, 403} and "Set-Cookie" not in headers and KEY.encode() not in body
    status, headers, _ = request(server, "/api/pair", method="POST",
        headers={"Origin": origin(server), "Content-Type": "application/json"}, body="not-json")
    assert status == 400 and "Set-Cookie" not in headers
    assert request(server)[0] == 401


def test_pairing_requires_exact_origin_and_bounded_plain_text(mobile_factory: Any) -> None:
    server, _ = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    for headers in (
        {"Content-Type": "text/plain"},
        {"Content-Type": "text/plain", "Origin": f"http://localhost:{server.server_port}"},
    ):
        status, response_headers, _ = request(server, "/api/pair", method="POST", headers=headers, body=KEY)
        assert status == 403 and "Set-Cookie" not in response_headers
    for body in ("", "x" * 129):
        status, response_headers, _ = request(server, "/api/pair", method="POST",
            headers={"Origin": origin(server), "Content-Type": "text/plain"}, body=body)
        assert status == 400 and "Set-Cookie" not in response_headers


def test_pairing_qr_is_host_local_but_phone_can_exchange_known_key(mobile_factory: Any) -> None:
    server, document = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    assert request(server, "/pairing")[0] == 200
    assert request(server, "/pairing.js")[0] == 200
    status, headers, body = request(server, "/pairing.svg")
    assert status == 200 and b"<svg" in body
    assert headers["Content-Type"] == "image/svg+xml" and headers["Cache-Control"] == "no-store"
    assert request(server, "/pairing.svg", method="HEAD")[2] == b""
    original_handler = server.RequestHandlerClass

    class SyntheticPhone(original_handler):
        def setup(self):
            super().setup()
            self.client_address = ("192.168.1.77", self.client_address[1])

    server.RequestHandlerClass = SyntheticPhone
    forwarded = {"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"}
    for path in ("/pairing", "/pairing.svg", "/pairing.js"):
        status, _, body = request(server, path, headers=forwarded)
        assert status == 403 and KEY.encode() not in body
    status, headers, body = request(server, "/api/pair-local", method="POST",
        headers={"Origin": origin(server), **forwarded})
    assert status == 403 and "Set-Cookie" not in headers and KEY.encode() not in body
    assert request(server)[0] == 401
    status, paired, _ = pair(server)
    assert status == 200
    cookie = paired["Set-Cookie"].split(";", 1)[0]
    assert request(server, headers={"Cookie": cookie})[2] == document


def test_host_reader_helper_is_constant_keyless_and_local_pairing_requires_exact_origin(mobile_factory: Any) -> None:
    server, document = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    other_key = "another-synthetic-mobile-session-" + "y" * 40
    other, _ = mobile_factory(listen="127.0.0.1", pairing_key=other_key)
    status, headers, script = request(server, "/pairing.js")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert KEY.encode() not in script and other_key.encode() not in script
    assert request(other, "/pairing.js")[2] == script
    assert b"/api/pair-local" in script and b"POST" in script
    for request_headers in ({}, {"Origin": "http://malicious.test"},
                            {"Origin": f"http://localhost:{server.server_port}"},
                            {"Origin": origin(server), "Sec-Fetch-Site": "cross-site"}):
        status, response_headers, _ = request(server, "/api/pair-local", method="POST", headers=request_headers)
        assert status == 403 and "Set-Cookie" not in response_headers
    status, response_headers, body = request(server, "/api/pair-local", method="POST",
        headers={"Origin": origin(server)})
    assert status == 200 and KEY.encode() not in body
    cookie = SimpleCookie()
    cookie.load(response_headers["Set-Cookie"])
    morsel = cookie["reader_session"]
    assert morsel["httponly"] and morsel["samesite"].lower() == "strict"
    assert request(server, headers={"Cookie": f"{morsel.key}={morsel.value}"})[2] == document


def test_session_expiry_revokes_cookie_pairing_and_qr(mobile_factory: Any, monkeypatch: Any) -> None:
    from newsresearch import result_viewer

    clock = [1000.0]
    monkeypatch.setattr(result_viewer.time, "monotonic", lambda: clock[0])
    server, _ = mobile_factory(listen="127.0.0.1", pairing_key=KEY, session_seconds=7200)
    status, paired, _ = pair(server)
    assert status == 200
    cookie = paired["Set-Cookie"].split(";", 1)[0]
    assert request(server, headers={"Cookie": cookie})[0] == 200
    clock[0] += 7200
    assert request(server, headers={"Cookie": cookie})[0] == 401
    assert pair(server)[0] == 401
    assert request(server, "/pairing")[0] == 403
    assert request(server, "/pairing.svg")[0] == 403
    assert request(server, "/pairing.js")[0] == 403
    status, headers, _ = request(server, "/api/pair-local", method="POST", headers={"Origin": origin(server)})
    assert status == 403 and "Set-Cookie" not in headers
    assert request(server, "/")[0] == 200


def test_cookie_does_not_bypass_cross_site_guards(mobile_factory: Any) -> None:
    server, _ = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    _, paired, _ = pair(server)
    cookie = paired["Set-Cookie"].split(";", 1)[0]
    for extra in ({"Host": "malicious.test"}, {"Origin": "https://malicious.test"},
                  {"Sec-Fetch-Site": "cross-site"}):
        assert request(server, headers={"Cookie": cookie, **extra})[0] == 403


def test_pairing_secrets_and_queries_are_not_written_to_server_output(mobile_factory: Any, capsys: Any) -> None:
    server, _ = mobile_factory(listen="127.0.0.1", pairing_key=KEY)
    pair(server)
    request(server, f"/unknown?key={KEY}")
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
