"""WebSocket server bus: fans out control events + audio frames to subscribers.

Publisher-only for v1 — incoming client messages are discarded.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import websockets
from loguru import logger
from pydantic import BaseModel, ValidationError
from websockets.asyncio.server import ServerConnection

from paty.bus.codec import pack_audio_frame
from paty.bus.events import (
    AudioStream,
    BusCommand,
    Event,
    EventType,
)

CommandHandler = Callable[[BusCommand], Awaitable[None] | None]

CONTROL_QUEUE_MAX = 256
AUDIO_QUEUE_MAX = 512


@dataclass(eq=False)
class _Subscriber:
    ws: ServerConnection
    control_queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=CONTROL_QUEUE_MAX)
    )
    audio_queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=AUDIO_QUEUE_MAX)
    )
    tasks: list[asyncio.Task] = field(default_factory=list)


class WebSocketBus:
    """A localhost WebSocket bus that publishes PATY session events.

    One connection = one subscriber. Each subscriber has independent bounded
    queues for control (JSON text) and audio (binary) frames. Control queue
    overflow disconnects the subscriber (never drop events); audio queue
    overflow drops the oldest frame (streaming best-effort).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._server: websockets.asyncio.server.Server | None = None
        self._subs: set[_Subscriber] = set()
        self._session_id: str = ""
        self._started_at_mono: float = 0.0
        self._event_seq: int = 0
        self._audio_seq: dict[AudioStream, int] = {}
        self._lock = asyncio.Lock()
        self._background: set[asyncio.Task] = set()
        self._on_command: CommandHandler | None = None

    def on_command(self, handler: CommandHandler | None) -> None:
        """Register a callback fired for every valid inbound BusCommand."""
        self._on_command = handler

    @property
    def session_id(self) -> str:
        return self._session_id

    def ts_ms(self) -> int:
        return int((time.monotonic() - self._started_at_mono) * 1000)

    async def start(self) -> None:
        self._session_id = uuid.uuid4().hex[:16]
        self._started_at_mono = time.monotonic()
        self._event_seq = 0
        self._audio_seq = {AudioStream.MIC: 0, AudioStream.AGENT: 0}
        self._server = await websockets.serve(self._handle_conn, self.host, self.port)
        logger.info(
            f"bus: listening on ws://{self.host}:{self.port} (session={self._session_id})"
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        # Cancel per-subscriber tasks and close sockets
        async with self._lock:
            subs = list(self._subs)
            self._subs.clear()
        for sub in subs:
            for t in sub.tasks:
                t.cancel()
            with contextlib.suppress(Exception):
                await sub.ws.close()
        logger.info("bus: stopped")

    async def _handle_conn(self, ws: ServerConnection) -> None:
        sub = _Subscriber(ws=ws)
        async with self._lock:
            self._subs.add(sub)
        logger.debug(f"bus: subscriber connected ({ws.remote_address})")
        sub.tasks = [
            asyncio.create_task(self._control_sender(sub)),
            asyncio.create_task(self._audio_sender(sub)),
            asyncio.create_task(self._reader(sub)),
        ]
        try:
            # Exit as soon as any task finishes (typically the reader on
            # client disconnect) and cancel the rest so the handler returns
            # and the WebSocket server can drain on shutdown.
            _, pending = await asyncio.wait(
                sub.tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            for t in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await t
        finally:
            async with self._lock:
                self._subs.discard(sub)
            logger.debug("bus: subscriber disconnected")

    async def _reader(self, sub: _Subscriber) -> None:
        # Inbound text frames are parsed as BusCommands and dispatched to the
        # registered handler. Binary frames + malformed JSON are dropped so
        # the socket doesn't fill kernel buffers.
        try:
            async for msg in sub.ws:
                if isinstance(msg, bytes) or self._on_command is None:
                    continue
                try:
                    cmd = BusCommand.model_validate_json(msg)
                except ValidationError:
                    logger.debug("bus: ignoring malformed command")
                    continue
                try:
                    result = self._on_command(cmd)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("bus: command handler raised")
        except websockets.exceptions.ConnectionClosed:
            pass

    async def _control_sender(self, sub: _Subscriber) -> None:
        try:
            while True:
                msg = await sub.control_queue.get()
                await sub.ws.send(msg)
        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
            pass

    async def _audio_sender(self, sub: _Subscriber) -> None:
        try:
            while True:
                msg = await sub.audio_queue.get()
                await sub.ws.send(msg)
        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
            pass

    async def _drop(self, sub: _Subscriber, reason: str) -> None:
        logger.warning(f"bus: dropping subscriber — {reason}")
        with contextlib.suppress(Exception):
            await sub.ws.close(code=1011, reason=reason[:123])

    def publish(
        self,
        event_type: EventType,
        data: BaseModel | dict[str, Any] | None = None,
    ) -> None:
        """Publish a control event to all subscribers. Non-blocking."""
        if self._server is None:
            return
        payload = {}
        if isinstance(data, BaseModel):
            payload = data.model_dump(exclude_none=True)
        elif isinstance(data, dict):
            payload = data
        self._event_seq += 1
        envelope = Event(
            seq=self._event_seq,
            ts_ms=self.ts_ms(),
            session_id=self._session_id,
            type=event_type,
            data=payload,
        )
        msg = envelope.model_dump_json()
        to_drop: list[_Subscriber] = []
        for sub in self._subs:
            try:
                sub.control_queue.put_nowait(msg)
            except asyncio.QueueFull:
                to_drop.append(sub)
        for sub in to_drop:
            task = asyncio.create_task(self._drop(sub, "control queue overflow"))
            self._background.add(task)
            task.add_done_callback(self._background.discard)

    def publish_audio(
        self,
        stream: AudioStream,
        sample_rate: int,
        channels: int,
        pcm: bytes,
    ) -> None:
        """Publish a PCM16LE audio frame to all subscribers. Non-blocking."""
        if self._server is None or not self._subs:
            return
        self._audio_seq[stream] = self._audio_seq.get(stream, 0) + 1
        frame = pack_audio_frame(
            stream=stream,
            sample_rate=sample_rate,
            channels=channels,
            seq=self._audio_seq[stream],
            ts_ms=self.ts_ms(),
            pcm=pcm,
        )
        for sub in self._subs:
            try:
                sub.audio_queue.put_nowait(frame)
            except asyncio.QueueFull:
                # Drop-oldest: best-effort streaming.
                with contextlib.suppress(asyncio.QueueEmpty):
                    sub.audio_queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    sub.audio_queue.put_nowait(frame)
