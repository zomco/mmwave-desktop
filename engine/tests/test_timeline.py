from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tracecue_engine import TimelineValidationError, dump_timeline, inspect_timeline, load_timeline


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "contracts" / "timeline" / "v1" / "examples" / "minimal.json"


class TimelineTests(unittest.TestCase):
    def payload(self) -> dict:
        return json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def assert_issue(self, payload: dict, code: str) -> None:
        with self.assertRaises(TimelineValidationError) as raised:
            inspect_timeline(payload)
        self.assertIn(code, {item.code for item in raised.exception.issues})

    def test_checked_in_example_round_trips(self) -> None:
        document = load_timeline(EXAMPLE)
        rendered = dump_timeline(document)
        reparsed = inspect_timeline(rendered).document
        self.assertEqual(document, reparsed)
        self.assertEqual("timeline.v1", document.schema_version)

    def test_inspection_hashes_exact_content(self) -> None:
        raw = EXAMPLE.read_bytes()
        first = inspect_timeline(raw)
        second = inspect_timeline(raw + b"\n")
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_rejects_timestamp_without_timezone(self) -> None:
        payload = self.payload()
        payload["intervals"][0]["start_at"] = "2026-08-12T08:12:03"
        self.assert_issue(payload, "TIMELINE_TIMEZONE_REQUIRED")

    def test_rejects_duplicate_channel_id(self) -> None:
        payload = self.payload()
        payload["channels"].append(copy.deepcopy(payload["channels"][0]))
        self.assert_issue(payload, "TIMELINE_DUPLICATE_CHANNEL")

    def test_rejects_unknown_channel_reference(self) -> None:
        payload = self.payload()
        payload["intervals"][0]["channel_id"] = "missing"
        self.assert_issue(payload, "TIMELINE_CHANNEL_UNKNOWN")

    def test_rejects_media_window_that_does_not_cover_interval(self) -> None:
        payload = self.payload()
        payload["intervals"][0]["media_window"]["start_at"] = "2026-08-12T08:12:04Z"
        self.assert_issue(payload, "TIMELINE_MEDIA_WINDOW_INVALID")

    def test_rejects_additive_fields_under_strict_v1(self) -> None:
        payload = self.payload()
        payload["unexpected"] = True
        self.assert_issue(payload, "TIMELINE_FIELD_UNKNOWN")

    def test_bounds_input_size_before_parsing(self) -> None:
        with self.assertRaises(TimelineValidationError) as raised:
            inspect_timeline(b"{}" * 10, maximum_bytes=4)
        self.assertEqual("TIMELINE_TOO_LARGE", raised.exception.issues[0].code)


if __name__ == "__main__":
    unittest.main()

