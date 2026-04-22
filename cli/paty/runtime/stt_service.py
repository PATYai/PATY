"""In-process STT via mlx-audio for Apple Silicon.

Wraps any mlx-audio STT model (Moonshine, Whisper, SenseVoice, etc.)
as a Pipecat SegmentedSTTService. Runs inference on the Metal GPU.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import numpy as np
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.utils.time import time_now_iso8601

DEFAULT_MODEL_REPO = "UsefulSensors/moonshine-base"


class MLXAudioSTTService(SegmentedSTTService):
    """Generic mlx-audio STT service for Apple Silicon.

    Works with any model supported by ``mlx_audio.stt.load()``:
    Moonshine, Whisper-MLX, SenseVoice, etc.

    The caller must pass a ``compute_executor`` — a single-worker
    ``ThreadPoolExecutor`` shared by every MLX service in the pipeline.
    Metal's command queue is not safe for concurrent encoding across OS
    threads; serializing all MLX work onto one thread is the only way to
    avoid ``A command encoder is already encoding to this command buffer``
    assertions.  Lifecycle of the executor belongs to the caller.
    """

    def __init__(
        self,
        *,
        compute_executor: ThreadPoolExecutor,
        model_repo: str = DEFAULT_MODEL_REPO,
        **kwargs,
    ):
        super().__init__(sample_rate=16000, **kwargs)
        self._executor = compute_executor
        self._model_repo = model_repo

        logger.info(f"Loading STT model: {model_repo}")
        self._model = self._executor.submit(self._load_model).result()
        logger.info("STT model loaded")

    def _load_model(self):
        from mlx_audio.stt import load

        return load(self._model_repo)

    def can_generate_metrics(self) -> bool:
        return True

    def _transcribe_sync(self, audio_float: np.ndarray) -> str:
        """Run synchronous MLX inference, return transcribed text."""
        import mlx.core as mx

        audio_mx = mx.array(audio_float)
        result = self._model.generate(audio_mx)
        return result.text.strip()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        if self._model is None:
            yield ErrorFrame(error="MLX Audio STT model not available")
            return

        await self.start_processing_metrics()

        audio_float = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            self._executor, partial(self._transcribe_sync, audio_float)
        )

        await self.stop_processing_metrics()

        if text:
            logger.debug(f"Transcription: [{text}]")
            yield TranscriptionFrame(
                text=text,
                user_id=self._user_id,
                timestamp=time_now_iso8601(),
                language=None,
            )
