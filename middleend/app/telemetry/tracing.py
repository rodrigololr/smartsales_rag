"""Request correlation: one trace_id per HTTP request, in error envelopes, logs and headers.

The id comes from the caller's X-Request-ID when it is a valid UUID (so the frontend can
correlate its own retries), otherwise it is generated. It is echoed in the response
header, forwarded to the backend worker and attached to every log line.
"""

import logging
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
LOG_FORMAT = (
    "%(asctime)s level=%(levelname)s logger=%(name)s event=%(message)s "
    "trace_id=%(trace_id)s session_id=%(session_id)s"
)
_MISSING = "-"

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def current_trace_id() -> str:
    """The request's trace_id; a fresh UUID outside a request (startup, background tasks)."""
    return trace_id_var.get() or str(uuid.uuid4())


def _valid_request_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


class RequestIdMiddleware:
    """Pure ASGI, outermost: the id must exist before rate limiting and survive streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        trace_id = _valid_request_id(incoming) or str(uuid.uuid4())
        # Not reset on exit: the app-wide 500 handler runs after this frame returns, in the
        # same task. Each ASGI request runs in its own task, so the value cannot leak.
        trace_id_var.set(trace_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = trace_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class TraceContextFilter(logging.Filter):
    """Fills trace_id from the request context and defaults session_id for every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "trace_id", None):
            record.trace_id = trace_id_var.get() or _MISSING
        if getattr(record, "session_id", None) is None:
            record.session_id = _MISSING
        return True


def build_log_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.addFilter(TraceContextFilter())
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


def configure_logging(level: int = logging.INFO) -> None:
    """key=value lines with trace_id and session_id (from `extra`) on the root logger."""
    logging.basicConfig(level=level, handlers=[build_log_handler()])
