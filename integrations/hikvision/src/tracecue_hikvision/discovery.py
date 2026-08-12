"""Bounded ONVIF WS-Discovery for local NVR onboarding."""

from __future__ import annotations

import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import IPv4Address, IPv4Network
from urllib.parse import unquote, urlsplit

from .models import DiscoveredDevice
from .xmlutil import local_name, parse_xml


_MULTICAST_ADDRESS = ("239.255.255.250", 3702)
_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_NETWORKS = 3
_MAX_SCAN_HOSTS = 3 * 254


def discover_devices(timeout_seconds: float = 2.5) -> tuple[DiscoveredDevice, ...]:
    """Discover devices with ONVIF first, then a bounded private-/24 ISAPI probe."""
    if not 0.5 <= timeout_seconds <= 5.0:
        raise ValueError("discovery timeout must be between 0.5 and 5 seconds")
    deadline = time.monotonic() + timeout_seconds
    devices = {
        (item.host, item.http_port, item.use_https): item
        for item in _discover_onvif(min(1.25, timeout_seconds * 0.4))
    }
    if time.monotonic() < deadline:
        for item in _discover_private_isapi(deadline):
            devices.setdefault((item.host, item.http_port, item.use_https), item)
    return tuple(sorted(devices.values(), key=lambda item: (item.name.lower(), item.host, item.http_port)))


def _discover_onvif(timeout_seconds: float) -> tuple[DiscoveredDevice, ...]:
    message_id = f"uuid:{uuid.uuid4()}"
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
        'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        '<e:Header>'
        f'<w:MessageID>{message_id}</w:MessageID>'
        '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
        '<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
        '</e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types>'
        '</d:Probe></e:Body></e:Envelope>'
    ).encode("utf-8")
    devices: dict[tuple[str, int, bool], DiscoveredDevice] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as client:
        client.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        client.settimeout(0.2)
        client.sendto(payload, _MULTICAST_ADDRESS)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and len(devices) < 256:
            try:
                response, _ = client.recvfrom(_MAX_RESPONSE_BYTES)
            except socket.timeout:
                continue
            except OSError:
                break
            for device in parse_discovery_response(response):
                devices[(device.host, device.http_port, device.use_https)] = device
    return tuple(devices.values())


def _discover_private_isapi(deadline: float) -> tuple[DiscoveredDevice, ...]:
    """Probe only port 80 on directly attached private /24s, without credentials."""
    hosts = [str(host) for network in _local_private_networks() for host in network.hosts()]
    hosts = hosts[:_MAX_SCAN_HOSTS]
    if not hosts:
        return ()
    pool = ThreadPoolExecutor(max_workers=min(96, len(hosts)), thread_name_prefix="tracecue-discovery")
    futures = {pool.submit(_probe_isapi_candidate, host, deadline): host for host in hosts}
    result: list[DiscoveredDevice] = []
    try:
        remaining = max(0.01, deadline - time.monotonic())
        for future in as_completed(futures, timeout=remaining):
            try:
                device = future.result()
            except OSError:
                continue
            if device is not None:
                result.append(device)
    except TimeoutError:
        pass
    finally:
        for future in futures:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
    return tuple(result)


def _local_private_networks() -> tuple[IPv4Network, ...]:
    addresses: set[IPv4Address] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(IPv4Address(item[4][0]))
    except (OSError, ValueError):
        pass
    networks = {
        IPv4Network(f"{address}/24", strict=False)
        for address in addresses
        if address.is_private and not address.is_loopback and not address.is_link_local
    }
    # Prefer normal LAN ranges over virtual 172.16/12 adapters when the cap is reached.
    return tuple(sorted(networks, key=lambda item: (not str(item).startswith("192.168."), str(item))))[:_MAX_NETWORKS]


def _probe_isapi_candidate(host: str, deadline: float) -> DiscoveredDevice | None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    # Embedded recorders can accept TCP quickly but need several hundred milliseconds
    # to construct their Digest challenge while the subnet probe is in flight.
    timeout = min(0.8, max(0.05, remaining))
    with socket.create_connection((host, 80), timeout=timeout) as client:
        client.settimeout(timeout)
        client.sendall(
            f"GET /ISAPI/System/deviceInfo HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode(
                "ascii"
            )
        )
        response = client.recv(8192)
    return parse_isapi_candidate_response(response, host)


def parse_isapi_candidate_response(content: bytes, host: str) -> DiscoveredDevice | None:
    """Recognize a conservative unauthenticated Hikvision/ISAPI candidate response."""
    if not content or len(content) > 8192:
        return None
    header = content.partition(b"\r\n\r\n")[0].lower()
    if not header.startswith(b"http/") or b" 401 " not in header.split(b"\r\n", 1)[0]:
        return None
    if b"www-authenticate: digest" not in header:
        return None
    if b"server: webs" not in header and b"content-type: application/xml" not in header:
        return None
    try:
        IPv4Address(host)
    except ValueError:
        return None
    return DiscoveredDevice(
        host=host,
        http_port=80,
        use_https=False,
        name=f"ISAPI candidate {host}",
        model=None,
        device_types=("NetworkVideoTransmitter",),
        discovery_protocol="isapi_private_subnet_probe",
    )


def parse_discovery_response(content: bytes) -> tuple[DiscoveredDevice, ...]:
    if not content or len(content) > _MAX_RESPONSE_BYTES:
        return ()
    try:
        root = parse_xml(content)
    except Exception:
        return ()
    matches = [item for item in root.iter() if local_name(item.tag) == "ProbeMatch"]
    result: list[DiscoveredDevice] = []
    for match in matches:
        values: dict[str, str] = {}
        for item in match.iter():
            name = local_name(item.tag)
            if name in {"XAddrs", "Scopes", "Types"} and item.text:
                values[name] = item.text.strip()
        scopes = tuple(unquote(value) for value in values.get("Scopes", "").split())
        device_types = tuple(value.rsplit(":", 1)[-1] for value in values.get("Types", "").split())
        name = _scope_value(scopes, "name")
        model = _scope_value(scopes, "hardware")
        for address in values.get("XAddrs", "").split():
            parsed = urlsplit(address)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            if parsed.username is not None or parsed.password is not None:
                continue
            use_https = parsed.scheme == "https"
            port = parsed.port or (443 if use_https else 80)
            result.append(
                DiscoveredDevice(
                    host=parsed.hostname,
                    http_port=port,
                    use_https=use_https,
                    name=name or model or parsed.hostname,
                    model=model,
                    device_types=device_types,
                )
            )
            break
    return tuple(result)


def _scope_value(scopes: tuple[str, ...], key: str) -> str | None:
    for scope in scopes:
        parsed = urlsplit(scope)
        marker = f"/{key.lower()}/"
        if parsed.scheme == "onvif" and marker in parsed.path.lower():
            position = parsed.path.lower().find(marker)
            value = parsed.path[position + len(marker):].strip("/")
            return value or None
    return None
