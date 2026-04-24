"""Binary audio frame codec.

Header layout (16 bytes, little-endian):

    offset  size  field
    0       1     magic        (0xA5)
    1       1     version      (protocol version)
    2       1     stream       (AudioStream: mic=1, agent=2)
    3       1     reserved     (0)
    4       2     sample_rate  (Hz)
    6       2     channels
    8       4     seq          (per-stream monotonic)
    12      4     ts_ms        (ms since session start)
    16+     ...   PCM16LE payload
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from paty.bus.events import PROTOCOL_VERSION, AudioStream

MAGIC = 0xA5
HEADER_FORMAT = "<BBBBHHII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

assert HEADER_SIZE == 16, "audio header must be 16 bytes"


@dataclass(frozen=True)
class AudioFrame:
    stream: AudioStream
    sample_rate: int
    channels: int
    seq: int
    ts_ms: int
    pcm: bytes


def pack_audio_frame(
    stream: AudioStream,
    sample_rate: int,
    channels: int,
    seq: int,
    ts_ms: int,
    pcm: bytes,
) -> bytes:
    header = struct.pack(
        HEADER_FORMAT,
        MAGIC,
        PROTOCOL_VERSION,
        int(stream),
        0,
        sample_rate & 0xFFFF,
        channels & 0xFFFF,
        seq & 0xFFFFFFFF,
        ts_ms & 0xFFFFFFFF,
    )
    return header + pcm


def unpack_audio_frame(data: bytes) -> AudioFrame:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"audio frame too short: {len(data)} bytes")
    (
        magic,
        version,
        stream,
        _reserved,
        sample_rate,
        channels,
        seq,
        ts_ms,
    ) = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    if magic != MAGIC:
        raise ValueError(f"bad magic byte: 0x{magic:02x}")
    if version != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version: {version}")
    return AudioFrame(
        stream=AudioStream(stream),
        sample_rate=sample_rate,
        channels=channels,
        seq=seq,
        ts_ms=ts_ms,
        pcm=bytes(data[HEADER_SIZE:]),
    )
