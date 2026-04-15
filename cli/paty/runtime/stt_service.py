"""In-process STT via mlx-audio for Apple Silicon.

Wraps any mlx-audio STT model (Moonshine, Whisper, SenseVoice, etc.)
as a Pipecat SegmentedSTTService. Runs inference on the Metal GPU.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from functools import partial

import numpy as np
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.utils.time import time_now_iso8601

DEFAULT_MODEL_REPO = "mlx-community/whisper-small-mlx"


class MLXAudioSTTService(SegmentedSTTService):
    """Generic mlx-audio STT service for Apple Silicon.

    Works with any model supported by ``mlx_audio.stt.load()``:
    Moonshine, Whisper-MLX, SenseVoice, etc.
    """

    def __init__(
        self,
        *,
        model_repo: str = DEFAULT_MODEL_REPO,
        no_speech_prob: float = 0.4,
        **kwargs,
    ):
        super().__init__(sample_rate=16000, **kwargs)
        self._no_speech_prob = no_speech_prob

        from mlx_audio.stt import load

        logger.info(f"Loading STT model: {model_repo}")
        self._model = load(model_repo)

        # Some mlx-community whisper repos only ship weights + config,
        # missing the HuggingFace preprocessor/tokenizer files that
        # WhisperProcessor needs.  Fall back to loading the processor
        # from the original openai repo which always has them.
        if not self._has_processor():
            self._install_processor_fallback(model_repo)

        logger.info("STT model loaded")

    def _has_processor(self) -> bool:
        """Check whether the loaded model has a usable HuggingFace processor."""
        processor = getattr(self._model, "_processor", None)
        return processor is not None

    def _install_processor_fallback(self, model_repo: str) -> None:
        """Load WhisperProcessor from the original openai repo as a fallback.

        MLX-community whisper repos often only contain weights + config.
        The processor/tokenizer can be loaded from the corresponding
        openai/whisper-* repo instead.
        """
        # Map mlx-community repos to their openai source
        processor_sources = {
            "mlx-community/whisper-tiny-mlx": "openai/whisper-tiny",
            "mlx-community/whisper-base-mlx": "openai/whisper-base",
            "mlx-community/whisper-small-mlx": "openai/whisper-small",
            "mlx-community/whisper-medium-mlx": "openai/whisper-medium",
            "mlx-community/whisper-large-mlx": "openai/whisper-large",
            "mlx-community/whisper-large-v2-mlx": "openai/whisper-large-v2",
            "mlx-community/whisper-large-v3-mlx": "openai/whisper-large-v3",
        }
        source = processor_sources.get(model_repo)
        if not source:
            logger.warning(
                f"No processor fallback for {model_repo} — transcription will fail"
            )
            return

        try:
            from transformers import WhisperProcessor

            logger.info(
                f"Loading WhisperProcessor from {source} (not bundled in {model_repo})"
            )
            self._model._processor = WhisperProcessor.from_pretrained(source)
            logger.info("WhisperProcessor loaded successfully")
        except Exception as exc:
            logger.error(f"Failed to load WhisperProcessor from {source}: {exc}")

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
            None, partial(self._transcribe_sync, audio_float)
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
