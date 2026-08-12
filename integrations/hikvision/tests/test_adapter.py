from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from tracecue_hikvision import (
    AuthenticationError,
    HikvisionAdapter,
    HttpResponse,
    PaginationError,
    RecordingQuery,
    UnsafePayloadError,
    UpstreamError,
)


FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)


class FixtureTransport:
    def __init__(self, responses: dict[tuple[str, str], list[bytes] | bytes | Exception]):
        self.responses = responses
        self.requests: list[tuple[str, str, bytes | None]] = []

    def request(self, method, path, *, body=None, headers=None, maximum_bytes=2 * 1024 * 1024):
        self.requests.append((method, path, body))
        value = self.responses[(method, path)]
        if isinstance(value, list):
            content = value.pop(0)
        else:
            content = value
        if isinstance(content, Exception):
            raise content
        return HttpResponse(200, {}, content)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class AdapterTests(unittest.TestCase):
    def adapter(self, search: bytes | None = None) -> HikvisionAdapter:
        responses = {
            ("GET", "/ISAPI/System/deviceInfo"): fixture("device_info.xml"),
            ("GET", "/ISAPI/System/time"): fixture("time.xml"),
            ("GET", "/ISAPI/System/Video/inputs/channels"): fixture("channels.xml"),
        }
        if search is not None:
            responses[("POST", "/ISAPI/ContentMgmt/search")] = search
        return HikvisionAdapter(FixtureTransport(responses), now=lambda: NOW)

    def test_probe_records_per_endpoint_evidence_without_promoting_unknowns(self) -> None:
        report = self.adapter().probe()
        self.assertTrue(report.reachable)
        self.assertTrue(report.authenticated)
        states = {item.capability: item.state for item in report.capabilities}
        self.assertEqual("supported", states["device_info"])
        self.assertEqual("supported", states["channel_discovery"])
        self.assertEqual("unknown", states["record_search"])
        self.assertEqual("DS-REDACTED", report.device.model)
        self.assertNotIn("REDACTED-SERIAL", repr(report.device))

    def test_probe_keeps_established_authentication_when_secondary_endpoints_deny_access(self) -> None:
        adapter = self.adapter()
        adapter.transport.responses[("GET", "/ISAPI/System/time")] = AuthenticationError(
            "denied"
        )
        adapter.transport.responses[
            ("GET", "/ISAPI/System/Video/inputs/channels")
        ] = AuthenticationError("denied")
        adapter.transport.responses[
            ("GET", "/ISAPI/ContentMgmt/InputProxy/channels/status")
        ] = AuthenticationError("denied")
        adapter.transport.responses[
            ("GET", "/ISAPI/ContentMgmt/InputProxy/channels/status")
        ] = AuthenticationError("denied")

        report = adapter.probe()

        self.assertTrue(report.reachable)
        self.assertTrue(report.authenticated)
        self.assertEqual("DS-REDACTED", report.device.model)
        states = {item.capability: item.state for item in report.capabilities}
        self.assertEqual("degraded", states["device_time"])
        self.assertEqual("degraded", states["channel_discovery"])
        self.assertEqual(
            {"DEVICE_TIME_ACCESS_DENIED", "CHANNEL_DISCOVERY_ACCESS_DENIED"},
            {warning["code"] for warning in report.warnings},
        )

    def test_nvr_probe_falls_back_to_input_proxy_channel_status(self) -> None:
        adapter = self.adapter()
        adapter.transport.responses[
            ("GET", "/ISAPI/System/Video/inputs/channels")
        ] = AuthenticationError("not available for this NVR")
        adapter.transport.responses[
            ("GET", "/ISAPI/ContentMgmt/InputProxy/channels/status")
        ] = fixture("input_proxy_channel_status.xml")

        report = adapter.probe()
        channels = adapter.list_channels()

        evidence = {
            item.capability: item for item in report.capabilities
        }["channel_discovery"]
        self.assertEqual("supported", evidence.state)
        self.assertEqual(
            "/ISAPI/ContentMgmt/InputProxy/channels/status", evidence.endpoint
        )
        self.assertEqual("1", channels[0].external_id)
        self.assertEqual("Front door", channels[0].name)
        self.assertTrue(channels[0].enabled)
        self.assertEqual(("101", "102"), channels[0].stream_track_ids)
        self.assertFalse(channels[1].enabled)

    def test_channel_identity_keeps_external_and_track_ids_separate(self) -> None:
        channels = self.adapter().list_channels()
        self.assertEqual("1", channels[0].external_id)
        self.assertEqual(("101", "102"), channels[0].stream_track_ids)
        self.assertFalse(channels[1].enabled)

    def test_event_audit_summarizes_rule_without_exposing_raw_configuration(self) -> None:
        adapter = self.adapter()
        adapter.transport.responses[
            ("GET", "/ISAPI/System/Video/inputs/channels/1/motionDetection")
        ] = fixture("motion_detection.xml")
        adapter.transport.responses[
            ("GET", "/ISAPI/Event/triggers/VMD-1")
        ] = fixture("event_trigger.xml")
        for endpoint in (
            "/ISAPI/Smart/LineDetection/101", "/ISAPI/Smart/FieldDetection/101"
        ):
            adapter.transport.responses[("GET", endpoint)] = UpstreamError("unsupported")

        report = adapter.inspect_event_settings(adapter.list_channels()[:1])

        motion = next(item for item in report.rules if item.event_type == "motion")
        self.assertEqual("supported", motion.state)
        self.assertTrue(motion.enabled)
        self.assertTrue(motion.notification_configured)
        self.assertEqual(60, motion.sensitivity)
        self.assertEqual(1, motion.region_count)
        self.assertEqual(1, motion.schedule_block_count)
        self.assertNotIn("beginTime", repr(motion))

    def test_search_parses_spans_and_explicit_gap(self) -> None:
        adapter = self.adapter(fixture("search_page.xml"))
        query = RecordingQuery("1", "101", NOW, NOW.replace(minute=1), page_size=40)
        page = adapter.search_recordings(query)
        self.assertTrue(page.complete)
        self.assertEqual(2, len(page.items))
        resolution = adapter.resolve_media(page.items, NOW, NOW.replace(second=30))
        self.assertFalse(resolution.complete)
        self.assertEqual((NOW.replace(second=10), NOW.replace(second=15)), resolution.missing_spans[0])
        self.assertNotIn("rtsp://", repr(page.items[0]))

    def test_search_request_escapes_track_id(self) -> None:
        adapter = self.adapter(fixture("search_page.xml"))
        query = RecordingQuery("1", "101&bad", NOW, NOW.replace(minute=1), page_size=40)
        adapter.search_recordings(query)
        body = adapter.transport.requests[-1][2]
        self.assertIn(b"<trackIDList>", body)
        self.assertIn(b"101&amp;bad", body)
        self.assertNotIn(b"<trackList>", body)
        search_id = re.search(rb"<searchID>([^<]+)</searchID>", body)
        self.assertIsNotNone(search_id)
        assert search_id is not None
        self.assertRegex(
            search_id.group(1).decode(),
            r"^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        )

    def test_rejects_xml_entities(self) -> None:
        malicious = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
        adapter = self.adapter()
        adapter.transport.responses[("GET", "/ISAPI/System/Video/inputs/channels")] = malicious
        with self.assertRaises(UnsafePayloadError):
            adapter.list_channels()

    def test_rejects_credential_bearing_locator(self) -> None:
        unsafe_locator = b"rtsp://" + b"user" + b":" + b"pass" + b"@192.0.2.10"
        content = fixture("search_page.xml").replace(b"rtsp://192.0.2.10", unsafe_locator, 1)
        adapter = self.adapter(content)
        query = RecordingQuery("1", "101", NOW, NOW.replace(minute=1), page_size=40)
        with self.assertRaises(UnsafePayloadError):
            adapter.search_recordings(query)

    def test_normalizes_http_port_misreported_in_rtsp_locator(self) -> None:
        content = fixture("search_page.xml").replace(
            b"rtsp://192.0.2.10", b"rtsp://192.0.2.10:80", 1
        )
        adapter = self.adapter(content)
        query = RecordingQuery("1", "101", NOW, NOW.replace(minute=1), page_size=40)

        page = adapter.search_recordings(query)

        self.assertEqual(554, urlsplit(page.items[0].playback_locator).port)

    def test_pagination_detects_non_progressing_page(self) -> None:
        content = fixture("search_page.xml").replace(b"NO MORE MATCHES", b"MORE MATCHES   ")
        content = content.replace(b"<numOfMatches>2</numOfMatches>", b"<numOfMatches>0</numOfMatches>")
        adapter = self.adapter(content)
        query = RecordingQuery("1", "101", NOW, NOW.replace(minute=1), page_size=1)
        with self.assertRaises(PaginationError):
            adapter.search_all_recordings(query)


if __name__ == "__main__":
    unittest.main()
