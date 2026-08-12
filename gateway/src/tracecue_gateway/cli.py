"""HA-free gateway command-line launcher."""

from __future__ import annotations

import argparse
import json
import signal
import threading
from pathlib import Path

from tracecue_engine import SourceChannel, dump_timeline, parse_rfc3339

from .acquisition import JsonLineTcpAdapter
from .clock import ClockHealth, ClockPolicy
from .detector import TraverseDetector, TraversePolicy
from .service import GatewayService
from .storage import GatewayStore


def main() -> None:
    parser = argparse.ArgumentParser(description="TraceCue always-on timeline gateway")
    parser.add_argument("config", type=Path, help="JSON configuration file")
    parser.add_argument("--export", type=Path, help="write timeline.v1 instead of collecting")
    parser.add_argument("--from", dest="from_at", help="export start with explicit offset")
    parser.add_argument("--to", dest="to_at", help="export end with explicit offset")
    args = parser.parse_args()
    values = json.loads(args.config.read_text(encoding="utf-8"))
    data_path = Path(values["data_path"])
    store = GatewayStore(data_path)
    source_id = values["source_id"]
    channel_id = values["channel_id"]
    channel_label = values.get("channel_label", channel_id)
    if args.export:
        if not args.from_at or not args.to_at:
            parser.error("--export requires --from and --to")
        document = store.export(
            source_id=source_id,
            channel=SourceChannel(channel_id, channel_label, "mmwave"),
            start_at=parse_rfc3339(args.from_at, "from"),
            end_at=parse_rfc3339(args.to_at, "to"),
            complete=bool(values.get("always_on_since")),
        )
        args.export.write_text(dump_timeline(document), encoding="utf-8")
        return
    adapter = JsonLineTcpAdapter(
        values["host"],
        int(values["port"]),
        source_id=source_id,
        channel_id=channel_id,
        model_identity=values.get("model_identity", "uncertified"),
    )
    service = GatewayService(
        adapter,
        TraverseDetector(source_id, channel_id, TraversePolicy(**values.get("traverse_policy", {}))),
        ClockHealth(ClockPolicy(**values.get("clock_policy", {}))),
        store,
    )
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    service.run_forever(stop)


if __name__ == "__main__":
    main()

