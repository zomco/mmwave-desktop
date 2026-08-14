"""Explicit, token-scoped LAN sharing for one generated clip."""

from __future__ import annotations

import html
import ipaddress
import secrets
import socket
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SHARE_TTL_SECONDS = 15 * 60
MAX_ACTIVE_SHARES = 32


@dataclass(frozen=True, slots=True)
class ShareTicket:
    clip_id: str
    token: str
    path: Path
    title: str
    expires_at_ms: int


class LanClipShareServer:
    """Serve only capability-token clip pages on an ephemeral private-LAN port."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tickets: dict[str, ShareTicket] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._bind_ip: str | None = None

    def create_share(
        self,
        *,
        clip_id: str,
        path: Path,
        title: str,
        route_target: str,
    ) -> dict[str, Any]:
        if not path.is_file():
            raise OSError("Clip file is unavailable")
        bind_ip = _private_route_address(route_target)
        with self._lock:
            self._remove_expired_locked()
            if self._server is None:
                handler = _handler_for(self)
                self._server = ThreadingHTTPServer((bind_ip, 0), handler)
                self._server.daemon_threads = True
                self._bind_ip = bind_ip
                self._thread = threading.Thread(
                    target=self._server.serve_forever,
                    name="tracecue-lan-clip-share",
                    daemon=True,
                )
                self._thread.start()
            elif self._bind_ip != bind_ip:
                bind_ip = self._bind_ip or bind_ip
            if len(self._tickets) >= MAX_ACTIVE_SHARES:
                oldest = min(self._tickets.values(), key=lambda item: item.expires_at_ms)
                self._tickets.pop(oldest.token, None)
            token = secrets.token_urlsafe(32)
            expires_at_ms = int(time.time() * 1000) + SHARE_TTL_SECONDS * 1000
            self._tickets[token] = ShareTicket(
                clip_id=clip_id,
                token=token,
                path=path.resolve(),
                title=title[:200],
                expires_at_ms=expires_at_ms,
            )
            port = int(self._server.server_address[1])
        return {
            "clip_id": clip_id,
            "url": f"http://{bind_ip}:{port}/s/{token}",
            "expires_at_ms": expires_at_ms,
        }

    def ticket(self, token: str) -> ShareTicket | None:
        with self._lock:
            self._remove_expired_locked()
            return self._tickets.get(token)

    def stop(self) -> None:
        with self._lock:
            server = self._server
            self._server = None
            self._tickets.clear()
        if server is not None:
            server.shutdown()
            server.server_close()

    def _remove_expired_locked(self) -> None:
        now = int(time.time() * 1000)
        self._tickets = {
            token: ticket for token, ticket in self._tickets.items()
            if ticket.expires_at_ms > now and ticket.path.is_file()
        }


def _private_route_address(target: str) -> str:
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((target, 9))
            candidates.append(str(probe.getsockname()[0]))
    except OSError:
        pass
    try:
        candidates.extend(
            item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    for value in candidates:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.version == 4 and address.is_private and not address.is_loopback and not address.is_link_local:
            return value
    raise OSError("No private LAN address is available for sharing")


def _handler_for(owner: LanClipShareServer):
    class ClipShareHandler(BaseHTTPRequestHandler):
        server_version = "TraceCueShare/1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._serve(head_only=False)

        def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._serve(head_only=True)

        def log_message(self, _format: str, *_args: object) -> None:
            # Capability tokens and private addresses must never enter logs.
            return

        def _serve(self, *, head_only: bool) -> None:
            parts = urlsplit(self.path).path.strip("/").split("/")
            if len(parts) not in {2, 3} or parts[0] != "s":
                self._empty(404)
                return
            ticket = owner.ticket(parts[1])
            if ticket is None:
                self._empty(404)
                return
            if len(parts) == 2:
                self._page(ticket, head_only=head_only)
                return
            if parts[2] != "video.mp4":
                self._empty(404)
                return
            self._video(ticket, head_only=head_only)

        def _page(self, ticket: ShareTicket, *, head_only: bool) -> None:
            title = html.escape(ticket.title or "TraceCue 视频片段")
            video_path = f"/s/{ticket.token}/video.mp4"
            body = f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"robots\" content=\"noindex,nofollow\"><title>{title}</title><style>body{{margin:0;background:#102e29;color:#fff;font-family:system-ui;padding:24px}}main{{max-width:760px;margin:auto}}video{{width:100%;background:#000;border-radius:16px}}a{{display:block;margin-top:18px;padding:14px;text-align:center;border-radius:12px;background:#059669;color:white;text-decoration:none;font-weight:700}}p{{color:#bbf7d0;line-height:1.6}}</style></head><body><main><h1>{title}</h1><p>此链接由 TraceCue 临时生成，仅在当前局域网内短期有效。</p><video src=\"{video_path}\" controls playsinline preload=\"metadata\"></video><a href=\"{video_path}\" download=\"tracecue-{html.escape(ticket.clip_id)}.mp4\">保存 MP4</a></main></body></html>""".encode("utf-8")
            self.send_response(200)
            self._security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)

        def _video(self, ticket: ShareTicket, *, head_only: bool) -> None:
            size = ticket.path.stat().st_size
            start, end = 0, size - 1
            status = 200
            range_header = self.headers.get("Range")
            if range_header:
                parsed = _parse_range(range_header, size)
                if parsed is None:
                    self.send_response(416)
                    self._security_headers()
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                start, end = parsed
                status = 206
            length = end - start + 1
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Disposition", f'inline; filename="tracecue-{ticket.clip_id}.mp4"')
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if head_only:
                return
            with ticket.path.open("rb") as source:
                source.seek(start)
                remaining = length
                while remaining:
                    block = source.read(min(64 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; media-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
            )

        def _empty(self, status: int) -> None:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

    return ClipShareHandler


def _parse_range(value: str, size: int) -> tuple[int, int] | None:
    if not value.startswith("bytes=") or "," in value:
        return None
    bounds = value.removeprefix("bytes=").split("-", 1)
    if len(bounds) != 2:
        return None
    try:
        if bounds[0]:
            start = int(bounds[0])
            end = int(bounds[1]) if bounds[1] else size - 1
        else:
            suffix = int(bounds[1])
            if suffix <= 0:
                return None
            start, end = max(0, size - suffix), size - 1
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)
