"""Renew a turn while waiting on the backend; stop delivery when ownership is lost."""

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress

from app.sessions.store import SessionStore, TurnLost
from app.sse.models import BackendStream

logger = logging.getLogger(__name__)


class LeaseStream:
    def __init__(
        self,
        backend: BackendStream,
        store: SessionStore,
        session_id: str,
        request_id: str,
        token: str,
        interval: float,
        ttl: float,
    ) -> None:
        self._backend, self._store = backend, store
        self._session, self._request, self._token = session_id, request_id, token
        self._interval, self._ttl = interval, ttl
        self._heartbeat: asyncio.Task[None] | None = None
        self._lost = asyncio.Event()
        self._closed = False

    def __aiter__(self) -> AsyncIterator[Mapping[str, object]]:
        return self

    async def _renew(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                async with asyncio.timeout(self._ttl - self._interval):
                    if not await self._store.renew(self._session, self._request, self._token):
                        break
        except Exception:
            logger.warning("session_lease_renewal_failed", extra={"session_id": self._session})
        self._lost.set()

    async def __anext__(self) -> Mapping[str, object]:
        if self._heartbeat is None:
            # Verify the lease before even starting the provider, including delayed HTTP delivery.
            if not await self._store.renew(self._session, self._request, self._token):
                raise TurnLost("Session lease lost before generation")
            self._heartbeat = asyncio.create_task(self._renew())
        read = asyncio.create_task(anext(self._backend))
        lost = asyncio.create_task(self._lost.wait())
        try:
            await asyncio.wait((read, lost), return_when=asyncio.FIRST_COMPLETED)
            if self._lost.is_set():
                raise TurnLost("Session lease lost during generation")
            return await read
        finally:
            for task in (read, lost):
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                    await task

    async def check_delivery(self) -> None:
        if self._lost.is_set():
            raise TurnLost("Session lease lost before publication")

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat
        await self._backend.aclose()
