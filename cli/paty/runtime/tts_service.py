"""In-process Kokoro TTS via mlx-audio for Apple Silicon."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import numpy as np
from loguru import logger
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts

# Default HuggingFace model repo for Kokoro
DEFAULT_MODEL_REPO = "mlx-community/Kokoro-82M-bf16"
DEFAULT_VOICE = "af_bella"
DEFAULT_SAMPLE_RATE = 24000


@dataclass
class MLXAudioTTSSettings(TTSSettings):
    """Settings for MLXAudioTTSService."""


class MLXAudioTTSService(TTSService):
    """Kokoro TTS via mlx-audio — runs entirely in-process on Apple Silicon.

    Models are auto-downloaded from HuggingFace on first use and cached
    in ~/.cache/huggingface/.

    The caller must pass a ``compute_executor`` — a single-worker
    ``ThreadPoolExecutor`` shared with every other MLX service in the
    pipeline.  Both model load and inference (including the lazy Kokoro
    pipeline / misaki / espeak-ng setup triggered on first call) run on
    that thread.  See ``paty.runtime.gpu_executor`` for the rationale.
    """

    Settings = MLXAudioTTSSettings
    _settings: Settings

    def __init__(
        self,
        *,
        compute_executor: ThreadPoolExecutor,
        model_repo: str = DEFAULT_MODEL_REPO,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        lang_code: str = "a",
        settings: MLXAudioTTSSettings | None = None,
        **kwargs,
    ):
        default_settings = self.Settings(
            model=model_repo,
            voice=voice,
            language=None,
        )
        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            settings=default_settings,
            **kwargs,
        )

        self._model_repo = model_repo
        self._speed = speed
        self._lang_code = lang_code
        self._resampler = create_stream_resampler()
        self._executor = compute_executor

        logger.info(f"Loading TTS model: {self._model_repo}")
        self._model = self._executor.submit(self._load_model).result()
        logger.info("TTS model loaded")

    def _load_model(self):
        from mlx_audio.tts.utils import load_model

        return load_model(self._model_repo)

    def can_generate_metrics(self) -> bool:
        return True

    def _generate_sync(self, text: str) -> list[tuple[bytes, int]]:
        """Run synchronous MLX inference, return list of (pcm_bytes, sample_rate)."""
        chunks = []
        for result in self._model.generate(
            text=text,
            voice=self._settings.voice or DEFAULT_VOICE,
            speed=self._speed,
            lang_code=self._lang_code,
        ):
            audio_np = np.array(result.audio).flatten()
            audio_int16 = (audio_np * 32767).astype(np.int16).tobytes()
            sample_rate = getattr(result, "sample_rate", DEFAULT_SAMPLE_RATE)
            chunks.append((audio_int16, sample_rate))
        return chunks

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """Synthesize speech from text using mlx-audio."""
        logger.debug(f"{self}: Generating TTS [{text}]")

        try:
            await self.start_tts_usage_metrics(text)

            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(
                self._executor, partial(self._generate_sync, text)
            )

            for audio_bytes, in_sample_rate in chunks:
                await self.stop_ttfb_metrics()

                audio_data = await self._resampler.resample(
                    audio_bytes, in_sample_rate, self.sample_rate
                )
                yield TTSAudioRawFrame(
                    audio=audio_data,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    context_id=context_id,
                )
        except Exception as e:
            logger.error(f"{self} exception: {e}")
            yield ErrorFrame(error=f"MLX Audio TTS error: {e}")
        finally:
            await self.stop_ttfb_metrics()
