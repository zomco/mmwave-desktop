from pathlib import Path

from tracecue_hikvision import parse_discovery_response
from tracecue_hikvision.discovery import parse_isapi_candidate_response


FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_safe_onvif_probe_match() -> None:
    devices = parse_discovery_response((FIXTURES / "ws_discovery_probe_match.xml").read_bytes())

    assert len(devices) == 1
    assert devices[0].host == "192.0.2.55"
    assert devices[0].http_port == 8080
    assert devices[0].name == "Test Recorder"
    assert devices[0].model == "Fixture-NVR"
    assert devices[0].discovery_protocol == "onvif_ws_discovery"


def test_rejects_credential_bearing_discovery_address() -> None:
    content = (FIXTURES / "ws_discovery_probe_match.xml").read_bytes().replace(
        b"http://192.0.2.55:8080",
        b"http://" + b"fixture-user" + b":" + b"fixture-secret" + b"@192.0.2.55:8080",
    )

    assert parse_discovery_response(content) == ()


def test_recognizes_bounded_isapi_candidate_without_credentials() -> None:
    content = (
        b"HTTP/1.0 401 Unauthorized\r\n"
        b"Server: Webs\r\n"
        b"Content-Type: application/xml\r\n"
        b'WWW-Authenticate: Digest realm="redacted"\r\n\r\n'
    )

    device = parse_isapi_candidate_response(content, "192.0.2.55")

    assert device is not None
    assert device.discovery_protocol == "isapi_private_subnet_probe"


def test_rejects_generic_unauthenticated_http_service() -> None:
    content = b"HTTP/1.0 401 Unauthorized\r\nWWW-Authenticate: Basic realm=test\r\n\r\n"

    assert parse_isapi_candidate_response(content, "192.0.2.55") is None
