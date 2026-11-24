"""HueClient against a local fake bridge: TLS pinning, REST and the SSE stream."""

from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lightdeck.hue.client import (
    CertificateMismatchError,
    HueClient,
    HueUnauthorizedError,
    bridge_info,
    fetch_fingerprint,
)

KEY = "test-app-key"
LIGHT = {"id": "l1", "type": "light", "on": {"on": True}, "dimming": {"brightness": 50.0}}


class Handler(BaseHTTPRequestHandler):
    puts: list = []
    stream_hold = 0.5  # seconds the event stream stays open after the first event
    chunked = False  # HTTP/1.1 chunked transfer encoding, like a real bridge

    def log_message(self, *args):  # silence
        pass

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/0/config":
            return self._json(200, {"name": "Fake Bridge", "bridgeid": "ABC123", "apiversion": "1.65.0"})
        if self.headers.get("hue-application-key") != KEY:
            return self._json(403, {"errors": [{"description": "unauthorized user"}]})
        if self.path == "/clip/v2/resource":
            return self._json(200, {"errors": [], "data": [LIGHT]})
        if self.path == "/eventstream/clip/v2":
            chunked = Handler.chunked
            if chunked:
                self.protocol_version = "HTTP/1.1"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            if chunked:
                self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            event = [{"type": "update", "data": [{"id": "l1", "dimming": {"brightness": 12.0}}]}]
            for part in (b": hi\n\n", b"id: 1:0\ndata: " + json.dumps(event).encode() + b"\n\n"):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(part), part) if chunked else part)
            self.wfile.flush()
            threading.Event().wait(Handler.stream_hold)
            if chunked:
                self.wfile.write(b"0\r\n\r\n")
            self.close_connection = True
            return None
        return self._json(404, {"errors": [{"description": "not found"}]})

    def do_PUT(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        Handler.puts.append((self.path, json.loads(self.rfile.read(length))))
        self._json(200, {"errors": [], "data": [{"rid": "l1", "rtype": "light"}]})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.path == "/api":
            return self._json(200, [{"success": {"username": KEY, "clientkey": "CK"}}])
        self._json(200, {"errors": [], "data": [{"rid": "new-scene", "rtype": "scene"}]})


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):  # aborted handshakes are expected
        pass


@pytest.fixture(scope="module")
def bridge(tmp_path_factory):
    if not shutil.which("openssl"):
        pytest.skip("openssl not available")
    tmp = tmp_path_factory.mktemp("tls")
    cert, key = tmp / "cert.pem", tmp / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
         "-days", "1", "-subj", "/CN=fakebridge"],
        check=True, capture_output=True,
    )
    server = QuietServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"127.0.0.1:{server.server_address[1]}", server.server_address[1]
    server.shutdown()


def test_pinned_client_roundtrip(bridge):
    host, port = bridge
    fingerprint = fetch_fingerprint("127.0.0.1", port)
    assert bridge_info(host).bridge_id == "abc123"
    key, client_key = HueClient.pair(host, fingerprint, "lightdeck#test")
    assert (key, client_key) == (KEY, "CK")

    client = HueClient(host, KEY, fingerprint)
    assert client.get_all() == [LIGHT]
    client.put("light", "l1", {"on": {"on": False}})
    assert Handler.puts[-1] == ("/clip/v2/resource/light/l1", {"on": {"on": False}})
    assert client.post("scene", {"type": "scene"}) == "new-scene"

    stop = threading.Event()
    events = client.iter_events(stop)
    assert next(events) == []
    assert next(events)[0]["data"][0]["dimming"]["brightness"] == 12.0
    stop.set()


def test_wrong_fingerprint_is_rejected(bridge):
    host, _ = bridge
    client = HueClient(host, KEY, "00" * 32)
    with pytest.raises(CertificateMismatchError):
        client.get_all()


def test_bad_key_is_unauthorized(bridge):
    host, port = bridge
    client = HueClient(host, "wrong", fetch_fingerprint("127.0.0.1", port))
    with pytest.raises(HueUnauthorizedError):
        client.get_all()


@pytest.mark.parametrize("chunked", [False, True], ids=["plain", "chunked"])
def test_live_events_and_abort(bridge, chunked):
    """Events arrive while the stream stays open, and closing the app never hangs on it."""
    host, port = bridge
    Handler.stream_hold, Handler.chunked = 30, chunked
    try:
        client = HueClient(host, KEY, fetch_fingerprint("127.0.0.1", port))
        stop = threading.Event()
        events = client.iter_events(stop)
        assert next(events) == []
        started = time.monotonic()
        batch = next(events)  # must arrive now, not when the server hangs up 30 s later
        assert time.monotonic() - started < 2
        assert batch[0]["data"][0]["dimming"]["brightness"] == 12.0

        finished = threading.Event()

        def drain():
            for _ in events:
                pass
            finished.set()

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        time.sleep(0.2)
        started = time.monotonic()
        stop.set()
        client.abort_events()
        assert finished.wait(2), "reader still blocked after abort_events()"
        assert time.monotonic() - started < 1.0
    finally:
        Handler.stream_hold, Handler.chunked = 0.5, False
