"""HTTP client for the Hue bridge CLIP v2 API.

The bridge serves HTTPS with a self-signed certificate. On first contact we
record the certificate's SHA-256 fingerprint and from then on only talk to a
bridge presenting that exact certificate (trust on first use).
"""

from __future__ import annotations

import codecs
import hashlib
import json
import socket
import ssl
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterator

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from urllib3.poolmanager import PoolManager

DISCOVERY_URL = "https://discovery.meethue.com/"
TIMEOUT = 6
EVENT_READ_TIMEOUT = 120


class HueError(RuntimeError):
    """Any failure talking to the bridge."""


class HueUnauthorizedError(HueError):
    """The application key is no longer accepted by the bridge."""


class LinkButtonNotPressedError(HueError):
    """Pairing attempted before the bridge's link button was pressed."""


class CertificateMismatchError(HueError):
    """The bridge presented a different TLS certificate than the pinned one."""


@dataclass
class DiscoveredBridge:
    ip: str
    bridge_id: str = ""
    name: str = ""
    model: str = ""
    supports_v2: bool = True


class _PinnedAdapter(HTTPAdapter):
    def __init__(self, fingerprint: str) -> None:
        self._fingerprint = fingerprint
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):  # type: ignore[override]
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            assert_fingerprint=self._fingerprint,
            assert_hostname=False,
            **pool_kwargs,
        )


def fetch_fingerprint(ip: str, port: int = 443, timeout: float = TIMEOUT) -> str:
    try:
        pem = ssl.get_server_certificate((ip, port), timeout=timeout)
    except (OSError, ssl.SSLError) as exc:
        raise HueError(f"Could not reach a bridge at {ip}.") from exc
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def _unverified_get(url: str, timeout: float) -> Any:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        response = requests.get(url, timeout=timeout, verify=False)
    response.raise_for_status()
    return response.json()


def bridge_info(ip: str, timeout: float = 3) -> DiscoveredBridge:
    """Read the bridge's public (unauthenticated) config."""
    try:
        data = _unverified_get(f"https://{ip}/api/0/config", timeout)
    except (requests.RequestException, ValueError) as exc:
        raise HueError(f"No Hue bridge answered at {ip}.") from exc
    if not isinstance(data, dict) or "bridgeid" not in data:
        raise HueError(f"The device at {ip} doesn't look like a Hue bridge.")
    api_version = str(data.get("apiversion", "0"))
    try:
        supports_v2 = tuple(int(p) for p in api_version.split(".")[:2]) >= (1, 46)
    except ValueError:
        supports_v2 = True
    return DiscoveredBridge(
        ip=ip,
        bridge_id=str(data.get("bridgeid", "")).lower(),
        name=str(data.get("name", "Hue Bridge")),
        model=str(data.get("modelid", "")),
        supports_v2=supports_v2,
    )


def _mdns_ips(timeout: float) -> set[str]:
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        return set()

    found: set[str] = set()

    class Listener(ServiceListener):
        def add_service(self, zc, type_, name):  # noqa: ANN001
            info = zc.get_service_info(type_, name, timeout=int(timeout * 1000))
            if info:
                found.update(info.parsed_addresses())

        def update_service(self, zc, type_, name):  # noqa: ANN001
            pass

        def remove_service(self, zc, type_, name):  # noqa: ANN001
            pass

    try:
        zc = Zeroconf()
    except OSError:
        return set()
    try:
        ServiceBrowser(zc, "_hue._tcp.local.", Listener())
        threading.Event().wait(timeout)
    finally:
        zc.close()
    return {ip for ip in found if ":" not in ip}  # IPv4 only


def _cloud_ips(timeout: float) -> set[str]:
    try:
        response = requests.get(DISCOVERY_URL, timeout=timeout)
        response.raise_for_status()
        return {item["internalipaddress"] for item in response.json() if "internalipaddress" in item}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return set()


def discover_bridges(timeout: float = 3.0) -> list[DiscoveredBridge]:
    """Find bridges via mDNS and the Hue cloud discovery endpoint, in parallel."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        mdns = pool.submit(_mdns_ips, timeout)
        cloud = pool.submit(_cloud_ips, timeout + 2)
        ips = mdns.result() | cloud.result()

    bridges: dict[str, DiscoveredBridge] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(ips))) as pool:
        for future in [pool.submit(bridge_info, ip) for ip in sorted(ips)]:
            try:
                bridge = future.result()
            except HueError:
                continue
            bridges.setdefault(bridge.bridge_id or bridge.ip, bridge)
    return sorted(bridges.values(), key=lambda b: (b.name.lower(), b.ip))


def _error_text(payload: Any) -> str | None:
    if isinstance(payload, dict):
        errors = payload.get("errors") or []
        if errors:
            return "; ".join(str(e.get("description", e)) for e in errors)
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "error" in payload[0]:
        return str(payload[0]["error"].get("description", "Unknown bridge error"))
    return None


def _live_chunks(response: requests.Response) -> Iterator[bytes]:
    """Yield data as soon as it arrives.

    ``iter_content(chunk_size=None)`` waits for the connection to close when
    the stream isn't chunk-encoded, which would hold back every event.
    """
    read1 = getattr(response.raw, "read1", None)
    if read1 is None:  # urllib3 < 2
        yield from response.iter_content(chunk_size=1)
        return
    while True:
        data = read1(65536)
        if not data:
            return
        yield data


def _response_socket(response: requests.Response) -> socket.socket | None:
    """The OS socket under a streamed response (urllib3 internals, best effort)."""
    raw = response.raw
    candidates = [
        getattr(getattr(raw, "_connection", None), "sock", None),
        # http.client drops connection.sock for streamed responses; the socket
        # then lives only inside the response's buffered reader.
        getattr(getattr(getattr(getattr(raw, "_fp", None), "fp", None), "raw", None), "_sock", None),
    ]
    for sock in candidates:
        if isinstance(sock, socket.socket):
            return sock
    return None


class HueClient:
    """Thread-safe: each thread gets its own requests session."""

    def __init__(self, ip: str, app_key: str, fingerprint: str) -> None:
        self.ip = ip
        self.app_key = app_key
        self.fingerprint = fingerprint
        self._local = threading.local()
        self._event_socket: socket.socket | None = None

    # -- pairing -----------------------------------------------------------

    @staticmethod
    def pair(ip: str, fingerprint: str, device_type: str) -> tuple[str, str]:
        """Returns (application key, client key). Raises LinkButtonNotPressedError until pressed."""
        session = HueClient._make_session(fingerprint)
        payload = HueClient._send(
            session, "post", f"https://{ip}/api",
            json={"devicetype": device_type[:40], "generateclientkey": True},
        )
        if isinstance(payload, list):
            for item in payload:
                if "success" in item:
                    success = item["success"]
                    return str(success["username"]), str(success.get("clientkey", ""))
                error = item.get("error", {})
                if error.get("type") == 101:
                    raise LinkButtonNotPressedError("Press the link button on the bridge.")
                if error:
                    raise HueError(str(error.get("description", "Pairing failed.")))
        raise HueError("The bridge returned an unexpected pairing response.")

    # -- resources ---------------------------------------------------------

    def get_all(self) -> list[dict[str, Any]]:
        return self._request("get", "/clip/v2/resource").get("data", [])

    def put(self, rtype: str, rid: str, payload: dict[str, Any]) -> None:
        self._request("put", f"/clip/v2/resource/{rtype}/{rid}", json=payload)

    def post(self, rtype: str, payload: dict[str, Any]) -> str:
        data = self._request("post", f"/clip/v2/resource/{rtype}", json=payload).get("data", [])
        if not data:
            raise HueError("The bridge did not return the new resource id.")
        return str(data[0]["rid"])

    def delete(self, rtype: str, rid: str) -> None:
        self._request("delete", f"/clip/v2/resource/{rtype}/{rid}")

    # -- event stream ------------------------------------------------------

    def iter_events(self, stop: threading.Event) -> Iterator[list[dict[str, Any]]]:
        """Yields [] once connected, then each batch of events as it arrives."""
        session = self._make_session(self.fingerprint)
        try:
            response = session.get(
                f"https://{self.ip}/eventstream/clip/v2",
                headers={"hue-application-key": self.app_key, "Accept": "text/event-stream"},
                stream=True,
                timeout=(TIMEOUT, EVENT_READ_TIMEOUT),
            )
        except requests.exceptions.SSLError as exc:
            raise CertificateMismatchError("The bridge's certificate changed.") from exc
        except requests.RequestException as exc:
            raise HueError("Lost connection to the bridge.") from exc
        if response.status_code in (401, 403):
            raise HueUnauthorizedError("The bridge no longer accepts this app.")
        if response.status_code != 200:
            raise HueError(f"Event stream failed with HTTP {response.status_code}.")

        self._event_socket = _response_socket(response)
        buffer = ""
        data_lines: list[str] = []
        try:
            if stop.is_set():
                return
            yield []
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            for chunk in _live_chunks(response):
                if stop.is_set():
                    return
                buffer += decoder.decode(chunk)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif line == "" and data_lines:
                        try:
                            batch = json.loads("".join(data_lines))
                        except ValueError:
                            batch = []
                        data_lines = []
                        if isinstance(batch, list) and batch:
                            yield batch
        except (requests.RequestException, urllib3.exceptions.HTTPError, OSError, ValueError, AttributeError) as exc:
            if not stop.is_set():
                raise HueError("Lost connection to the bridge.") from exc
        finally:
            self._event_socket = None
            try:
                response.close()
            except Exception:  # noqa: BLE001
                pass

    def abort_events(self) -> None:
        """Unblock a reader stuck in iter_events. Safe to call from any thread.

        Closing the response from another thread deadlocks against the thread
        that is reading it, so instead shut the raw socket down: the blocked
        read returns immediately and the reading thread cleans up itself.
        """
        sock = self._event_socket
        if sock is not None:
            try:
                socket.socket.shutdown(sock, socket.SHUT_RDWR)
            except OSError:
                pass

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _make_session(fingerprint: str) -> requests.Session:
        session = requests.Session()
        session.verify = False  # identity is checked by fingerprint instead
        session.mount("https://", _PinnedAdapter(fingerprint))
        return session

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._make_session(self.fingerprint)
            session.headers["hue-application-key"] = self.app_key
            self._local.session = session
        return session

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        payload = self._send(self._session(), method, f"https://{self.ip}{path}", **kwargs)
        return payload if isinstance(payload, dict) else {"data": payload}

    @staticmethod
    def _send(session: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = session.request(method, url, timeout=TIMEOUT, **kwargs)
        except requests.exceptions.SSLError as exc:
            raise CertificateMismatchError(
                "The bridge's security certificate changed. Forget the bridge and pair again."
            ) from exc
        except requests.Timeout as exc:
            raise HueError("The bridge took too long to respond.") from exc
        except (requests.ConnectionError, socket.error) as exc:
            raise HueError("Could not reach the bridge. Check your network.") from exc
        except requests.RequestException as exc:
            raise HueError(f"Network error: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code in (401, 403):
            raise HueUnauthorizedError("The bridge no longer accepts this app. Pair it again.")
        message = _error_text(payload)
        if response.status_code >= 400:
            raise HueError(message or f"Bridge request failed (HTTP {response.status_code}).")
        if message and isinstance(payload, dict) and not payload.get("data"):
            raise HueError(message)
        if payload is None:
            raise HueError("The bridge returned an invalid response.")
        return payload
