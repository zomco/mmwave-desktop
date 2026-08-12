"""HTTP Digest transport with bounded reads and explicit TLS policy."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    HTTPSHandler,
    Request,
    build_opener,
)

from .errors import AuthenticationError, ResponseLimitError, UnsafePayloadError, UpstreamError
from .models import ConnectionConfig


DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        maximum_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> HttpResponse: ...


class DigestTransport:
    def __init__(self, connection: ConnectionConfig):
        self.connection = connection
        password_manager = HTTPPasswordMgrWithDefaultRealm()
        password_manager.add_password(
            None, connection.base_url, connection.username, connection.password
        )
        handlers: list[object] = [HTTPDigestAuthHandler(password_manager)]
        if connection.use_https:
            context = ssl.create_default_context()
            if not connection.verify_tls:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            handlers.append(HTTPSHandler(context=context))
        self._opener = build_opener(*handlers)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        maximum_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> HttpResponse:
        if not path.startswith("/"):
            raise ValueError("ISAPI path must start with /")
        request_headers = {"Accept": "application/xml, application/json"}
        request_headers.update(headers or {})
        request = Request(
            self.connection.base_url + path,
            data=body,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with self._opener.open(request, timeout=self.connection.timeout_seconds) as response:
                declared = response.headers.get("Content-Length")
                if declared:
                    try:
                        declared_size = int(declared)
                    except ValueError as exc:
                        raise UnsafePayloadError("NVR returned an invalid Content-Length header") from exc
                    if declared_size < 0:
                        raise UnsafePayloadError("NVR returned an invalid Content-Length header")
                    if declared_size > maximum_bytes:
                        raise ResponseLimitError("NVR response exceeds the configured size limit")
                content = response.read(maximum_bytes + 1)
                if len(content) > maximum_bytes:
                    raise ResponseLimitError("NVR response exceeds the configured size limit")
                return HttpResponse(response.status, dict(response.headers.items()), content)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthenticationError("NVR authentication failed") from exc
            raise UpstreamError(f"NVR returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise UpstreamError("NVR connection failed") from exc
