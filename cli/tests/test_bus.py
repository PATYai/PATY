"""Tests for the PATY event bus (codec + WebSocket server)."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
import websockets

from paty.bus import BusAction, BusCommand, EventType, WebSocketBus
from paty.bus.codec import HEADER_SIZE, pack_audio_frame, unpack_audio_frame
from paty.bus.events import AudioStream, SessionStarted


class TestAudioCodec:
    def test_header_is_sixteen_bytes(self):
        packed = pack_audio_frame(AudioStream.MIC, 16000, 1, 1, 0, b"")
        assert len(packed) == HEADER_SIZE

    def test_roundtrip_preserves_fields(self):
        pcm = os.urandom(640)
        packed = pack_audio_frame(AudioStream.AGENT, 24000, 1, 42, 1234, pcm)
        frame = unpack_audio_frame(packed)
        assert frame.stream == AudioStream.AGENT
        assert frame.sample_rate == 24000
        assert frame.channels == 1
        assert frame.seq == 42
        assert frame.ts_ms == 1234
        assert frame.pcm == pcm

    def test_bad_magic_rejected(self):
        packed = bytearray(pack_audio_frame(AudioStream.MIC, 16000, 1, 1, 0, b""))
        packed[0] = 0x00
        with pytest.raises(ValueError, match="bad magic"):
            unpack_audio_frame(bytes(packed))

    def test_truncated_rejected(self):
        with pytest.raises(ValueError, match="too short"):
            unpack_audio_frame(b"\x00" * 4)


@pytest.fixture
async def bus():
    """Start a bus on an ephemeral port, yield, then shut it down."""
    b = WebSocketBus(host="127.0.0.1", port=0)
    # Port=0 → OS picks free port. We need to surface it; do a one-time
    # bind via the running server to read back sockname.
    b.port = _find_free_port()
    await b.start()
    try:
        yield b
    finally:
        await b.stop()


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestWebSocketBus:
    async def test_publishes_control_event_to_subscriber(self, bus: WebSocketBus):
        async with websockets.connect(f"ws://127.0.0.1:{bus.port}") as client:
            await _wait_for_subs(bus, 1)
            bus.publish(
                EventType.SESSION_STARTED,
                SessionStarted(
                    persona="p",
                    profile="x",
                    platform="mlx",
                    stt="s",
                    llm="l",
                    tts="t",
                ),
            )
            msg = await asyncio.wait_for(client.recv(), timeout=1.0)

        event = json.loads(msg)
        assert event["type"] == "session.started"
        assert event["seq"] == 1
        assert event["session_id"] == bus.session_id
        assert event["data"]["persona"] == "p"

    async def test_publishes_audio_frame_to_subscriber(self, bus: WebSocketBus):
        pcm = b"\x00\x01" * 320
        async with websockets.connect(f"ws://127.0.0.1:{bus.port}") as client:
            await _wait_for_subs(bus, 1)
            bus.publish_audio(AudioStream.MIC, 16000, 1, pcm)
            msg = await asyncio.wait_for(client.recv(), timeout=1.0)

        assert isinstance(msg, bytes)
        frame = unpack_audio_frame(msg)
        assert frame.stream == AudioStream.MIC
        assert frame.sample_rate == 16000
        assert frame.pcm == pcm

    async def test_event_sequence_numbers_are_monotonic(self, bus: WebSocketBus):
        async with websockets.connect(f"ws://127.0.0.1:{bus.port}") as client:
            await _wait_for_subs(bus, 1)
            for _ in range(3):
                bus.publish(EventType.USER_TRANSCRIPT_FINAL, {"text": "hi"})
            seqs = []
            for _ in range(3):
                msg = await asyncio.wait_for(client.recv(), timeout=1.0)
                seqs.append(json.loads(msg)["seq"])

        assert seqs == [1, 2, 3]

    async def test_fans_out_to_multiple_subscribers(self, bus: WebSocketBus):
        async with (
            websockets.connect(f"ws://127.0.0.1:{bus.port}") as c1,
            websockets.connect(f"ws://127.0.0.1:{bus.port}") as c2,
        ):
            await _wait_for_subs(bus, 2)
            bus.publish(EventType.USER_TRANSCRIPT_FINAL, {"text": "hi"})
            m1 = await asyncio.wait_for(c1.recv(), timeout=1.0)
            m2 = await asyncio.wait_for(c2.recv(), timeout=1.0)

        assert json.loads(m1)["data"]["text"] == "hi"
        assert json.loads(m2)["data"]["text"] == "hi"

    async def test_publish_before_start_is_safe(self):
        b = WebSocketBus(port=_find_free_port())
        # No start() → no subscribers, should not raise.
        b.publish(EventType.LOG, {"level": "info", "module": "x", "message": "m"})
        b.publish_audio(AudioStream.MIC, 16000, 1, b"\x00")

    async def test_dispatches_inbound_command(self, bus: WebSocketBus):
        received: list[BusCommand] = []
        bus.on_command(received.append)
        async with websockets.connect(f"ws://127.0.0.1:{bus.port}") as client:
            await _wait_for_subs(bus, 1)
            await client.send(json.dumps({"action": "mute.toggle"}))
            await client.send(json.dumps({"action": "mute.set", "muted": True}))
            deadline = asyncio.get_event_loop().time() + 1.0
            while len(received) < 2:
                if asyncio.get_event_loop().time() > deadline:
                    raise TimeoutError(f"expected 2 cmds, got {len(received)}")
                await asyncio.sleep(0.01)

        assert received[0].action == BusAction.MUTE_TOGGLE
        assert received[1].action == BusAction.MUTE_SET
        assert received[1].muted is True

    async def test_ignores_malformed_command(self, bus: WebSocketBus):
        received: list[BusCommand] = []
        bus.on_command(received.append)
        async with websockets.connect(f"ws://127.0.0.1:{bus.port}") as client:
            await _wait_for_subs(bus, 1)
            await client.send("not json")
            await client.send(json.dumps({"action": "bogus"}))
            await client.send(json.dumps({"action": "mute.toggle"}))
            deadline = asyncio.get_event_loop().time() + 1.0
            while not received:
                if asyncio.get_event_loop().time() > deadline:
                    raise TimeoutError("expected the valid command to land")
                await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0].action == BusAction.MUTE_TOGGLE


async def _wait_for_subs(bus: WebSocketBus, n: int, timeout: float = 1.0) -> None:
    """Poll until the bus has registered ``n`` subscribers."""
    deadline = asyncio.get_event_loop().time() + timeout
    while len(bus._subs) < n:
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(f"expected {n} subs, got {len(bus._subs)}")
        await asyncio.sleep(0.01)
