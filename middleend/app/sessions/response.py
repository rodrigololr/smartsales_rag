"""Close an SSE iterator even when ASGI send fails before its first read."""

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.sse.stream import SSEStream


class SessionStreamingResponse(StreamingResponse):
    media_type = "text/event-stream"

    def __init__(self, stream: SSEStream, *, headers: dict[str, str]) -> None:
        super().__init__(stream, media_type=self.media_type, headers=headers)
        self._stream = stream

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self._stream.aclose()
