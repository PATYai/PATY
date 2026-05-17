"""Local audio transport for PATY, built on sounddevice.

A drop-in replacement for ``pipecat.transports.local.audio.LocalAudioTransport``
that uses `sounddevice <https://python-sounddevice.readthedocs.io/>`_ instead
of PyAudio. sounddevice's prebuilt wheels bundle libportaudio on macOS and
Windows, so users no longer need ``brew install portaudio`` for the happy path.
On Linux the system's ``libportaudio2`` is still required at runtime.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from loguru import logger
from pipecat.frames.frames import (
    InputAudioRawFrame,
    OutputAudioRawFrame,
    StartFrame,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams

try:
    import sounddevice as sd
except OSError as e:
    logger.error(f"sounddevice import failed: {e}")
    logger.error(
        "sounddevice needs libportaudio at runtime. On Linux install "
        "`libportaudio2` (e.g. `apt-get install libportaudio2`); macOS and "
        "Windows wheels bundle it."
    )
    raise


# 16-bit signed PCM. Matches pipecat's LocalAudioTransport.
_SAMPLE_DTYPE = "int16"
_BYTES_PER_SAMPLE = 2


class LocalAudioTransportParams(TransportParams):
    """Configuration for :class:`LocalAudioTransport`.

    ``input_device`` / ``output_device`` accept anything sounddevice's
    ``device`` argument accepts: an integer index from ``sd.query_devices()``,
    a substring of the device name, or ``None`` for the system default.
    """

    input_device: int | str | None = None
    output_device: int | str | None = None


class LocalAudioInputTransport(BaseInputTransport):
    """Captures mic audio via a sounddevice ``RawInputStream`` callback."""

    _params: LocalAudioTransportParams

    def __init__(self, params: LocalAudioTransportParams):
        super().__init__(params)
        self._in_stream: sd.RawInputStream | None = None
        self._sample_rate = 0

    async def start(self, frame: StartFrame):
        await super().start(frame)

        if self._in_stream:
            return

        self._sample_rate = (
            self._params.audio_in_sample_rate or frame.audio_in_sample_rate
        )
        # 20ms of audio per block, matching pipecat's PyAudio transport.
        blocksize = int(self._sample_rate / 100) * 2

        self._in_stream = sd.RawInputStream(
            samplerate=self._sample_rate,
            channels=self._params.audio_in_channels,
            dtype=_SAMPLE_DTYPE,
            blocksize=blocksize,
            device=self._params.input_device,
            callback=self._audio_in_callback,
        )
        self._in_stream.start()

        await self.set_transport_ready(frame)

    async def cleanup(self):
        await super().cleanup()
        if self._in_stream:
            self._in_stream.stop()
            self._in_stream.close()
            self._in_stream = None

    def _audio_in_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug(f"sounddevice input status: {status}")

        frame = InputAudioRawFrame(
            audio=bytes(indata),
            sample_rate=self._sample_rate,
            num_channels=self._params.audio_in_channels,
        )

        asyncio.run_coroutine_threadsafe(
            self.push_audio_frame(frame), self.get_event_loop()
        )


class LocalAudioOutputTransport(BaseOutputTransport):
    """Plays bot audio via a sounddevice ``RawOutputStream``.

    ``RawOutputStream.write`` blocks until the buffer accepts the data, so we
    dispatch it onto a dedicated executor exactly like pipecat's PyAudio path.
    """

    _params: LocalAudioTransportParams

    def __init__(self, params: LocalAudioTransportParams):
        super().__init__(params)
        self._out_stream: sd.RawOutputStream | None = None
        self._sample_rate = 0
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def start(self, frame: StartFrame):
        await super().start(frame)

        if self._out_stream:
            return

        self._sample_rate = (
            self._params.audio_out_sample_rate or frame.audio_out_sample_rate
        )

        self._out_stream = sd.RawOutputStream(
            samplerate=self._sample_rate,
            channels=self._params.audio_out_channels,
            dtype=_SAMPLE_DTYPE,
            device=self._params.output_device,
        )
        self._out_stream.start()

        await self.set_transport_ready(frame)

    async def cleanup(self):
        await super().cleanup()
        if self._out_stream:
            self._out_stream.stop()
            self._out_stream.close()
            self._out_stream = None
        self._executor.shutdown(wait=False)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        if not self._out_stream:
            return False
        await self.get_event_loop().run_in_executor(
            self._executor, self._out_stream.write, frame.audio
        )
        return True


class LocalAudioTransport(BaseTransport):
    """Bidirectional local audio transport using sounddevice."""

    def __init__(self, params: LocalAudioTransportParams):
        super().__init__()
        self._params = params
        self._input: LocalAudioInputTransport | None = None
        self._output: LocalAudioOutputTransport | None = None

    def input(self) -> FrameProcessor:
        if not self._input:
            self._input = LocalAudioInputTransport(self._params)
        return self._input

    def output(self) -> FrameProcessor:
        if not self._output:
            self._output = LocalAudioOutputTransport(self._params)
        return self._output
