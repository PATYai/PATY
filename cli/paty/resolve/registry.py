"""Service registries: (provider, platform) → Pipecat service factory.

Each factory receives a resolved config object (STTConfig, LLMConfig, TTSConfig)
with model/voice already filled in (from explicit override or profile default).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from paty.config.schema import LLMConfig, Platform, STTConfig, TTSConfig

# Type alias for factory functions
Factory = Callable[..., Any]

# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

STT_REGISTRY: dict[tuple[str, Platform], Factory] = {
    ("whisper", Platform.MLX): lambda cfg: _make_whisper(cfg, device="auto"),
    ("whisper", Platform.CUDA): lambda cfg: _make_whisper(cfg, device="cuda"),
    ("whisper", Platform.CPU): lambda cfg: _make_whisper(cfg, device="cpu"),
}


def _make_whisper(cfg: STTConfig, device: str) -> Any:
    from pipecat.services.whisper.stt import WhisperSTTService

    return WhisperSTTService(
        settings=WhisperSTTService.Settings(model=cfg.model),
        device=device,
    )


# ---------------------------------------------------------------------------
# LLM — all platforms use OpenAI-compat client pointed at managed server
# ---------------------------------------------------------------------------

LLM_REGISTRY: dict[tuple[str, Platform], Factory] = {
    ("ollama", Platform.MLX): lambda cfg: _make_openai_compat_llm(cfg),
    ("ollama", Platform.CUDA): lambda cfg: _make_openai_compat_llm(cfg),
    ("ollama", Platform.CPU): lambda cfg: _make_openai_compat_llm(cfg),
}


def _make_openai_compat_llm(cfg: LLMConfig) -> Any:
    from pipecat.services.openai.llm import OpenAILLMService

    return OpenAILLMService(
        model=cfg.model or "default",
        base_url=cfg.base_url or "http://localhost:11434/v1",
        api_key="local",
    )


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

TTS_REGISTRY: dict[tuple[str, Platform], Factory] = {
    ("kokoro", Platform.MLX): lambda cfg: _make_mlx_audio_tts(cfg),
    ("kokoro", Platform.CUDA): lambda cfg: _make_kokoro_http(cfg),
    ("kokoro", Platform.CPU): lambda cfg: _make_kokoro_http(cfg),
    ("piper", Platform.CPU): lambda cfg: _make_piper(cfg),
}


def _make_mlx_audio_tts(cfg: TTSConfig) -> Any:
    from paty.runtime.tts_service import MLXAudioTTSService

    return MLXAudioTTSService(
        voice=cfg.voice or "af_bella",
    )


def _make_kokoro_http(cfg: TTSConfig) -> Any:
    from pipecat.services.openai.tts import OpenAITTSService

    return OpenAITTSService(
        base_url=cfg.base_url or "http://localhost:8880/v1",
        api_key="local",
        voice=cfg.voice,
    )


def _make_piper(cfg: TTSConfig) -> Any:
    from pipecat.services.piper import PiperTTSService

    return PiperTTSService(
        settings=PiperTTSService.Settings(
            voice=cfg.voice,
        )
    )
