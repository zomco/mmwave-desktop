"""Adapter error hierarchy with stable product-facing codes."""


class HikvisionError(RuntimeError):
    code = "NVR_UPSTREAM_ERROR"


class AuthenticationError(HikvisionError):
    code = "AUTH_INVALID"


class ResponseLimitError(HikvisionError):
    code = "NVR_RESPONSE_TOO_LARGE"


class UnsafePayloadError(HikvisionError):
    code = "NVR_RESPONSE_UNSAFE"


class PaginationError(HikvisionError):
    code = "NVR_PAGINATION_INVALID"


class UpstreamError(HikvisionError):
    code = "NVR_UPSTREAM_ERROR"

