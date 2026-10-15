from __future__ import annotations

import http.client
import json
import threading

import pytest

from newsresearch.common import ResearchError
from newsresearch.result_viewer import create_server, saved_result
from newsresearch.storage import prepare_root


@pytest.fixture
def viewer(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ("index.html", "app.js", "app.css"):
        (assets / name).write_text("synthetic viewer asset", encoding="utf-8")
    data = json.dumps({"id": "synthetic", "question": "Synthetic question", "rows": []}).encode()
    server = create_server(data, assets, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, data
    server.shutdown()
    server.server_close()
    thread.join()


def request(viewer, path="/api/results", headers=None, method="GET"):
    server, _ = viewer
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_serves_exact_saved_document_without_new_processing(viewer):
    status, headers, body = request(viewer)
    assert status == 200 and body == viewer[1]
    assert headers["Cache-Control"] == "no-store"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Access-Control-Allow-Origin" not in headers
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert viewer[0].server_address[0] == "127.0.0.1"
    assert request(viewer, method="HEAD")[2] == b""


@pytest.mark.parametrize("path", ["/../result.json", "/%2e%2e/result.json", "/files/", "/research.sqlite3"])
def test_private_files_and_directory_listings_are_not_routes(viewer, path):
    status, _, body = request(viewer, path)
    assert status == 404 and body == b"Not found"


@pytest.mark.parametrize("headers", [
    {"Host": "malicious.test"}, {"Origin": "https://malicious.test"}, {"Sec-Fetch-Site": "cross-site"},
])
def test_rejects_cross_site_and_dns_rebinding_requests(viewer, headers):
    status, _, body = request(viewer, headers=headers)
    assert status == 403 and body == b"Forbidden"


def test_saved_result_preserves_original_bytes_and_rejects_unrecognized_files(tmp_path):
    root = prepare_root(tmp_path / "protected")
    path = root / "saved.json"
    content = b'{"id":"fixture", "question":"Synthetic", "rows":[]}\n'
    path.write_bytes(content)
    assert saved_result(path) == content
    path.write_text('{"unrelated":"file"}', encoding="utf-8")
    with pytest.raises(ResearchError, match="existing RAG result"):
        saved_result(path)


def test_never_loads_a_research_copy_from_git(tmp_path):
    root = tmp_path / "git-repo"
    (root / ".git").mkdir(parents=True)
    path = root / "result.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ResearchError, match="outside Git"):
        saved_result(path)
