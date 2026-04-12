"""Service resolver: config + platform → instantiated Pipecat services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paty.config.schema import LLMConfig, PipelineConfig, Platform, STTConfig, TTSConfig
from paty.hardware.profiles import ResolvedProfile
from paty.resolve.registry import LLM_REGISTRY, STT_REGISTRY, TTS_REGISTRY


@dataclass
class ResolvedServices:
    stt: Any
    llm: Any
    tts: Any


def resolve_stt(cfg: STTConfig, platform: Platform, profile: ResolvedProfile) -> Any:
    """Resolve STT config to a Pipecat service instance."""
    if cfg.model is None:
        cfg = cfg.model_copy(update={"model": profile.stt_model})

    key = (cfg.provider, platform)
    factory = STT_REGISTRY.get(key)
    if factory is None:
        msg = f"No STT service registered for ({cfg.provider!r}, {platform.value!r})"
        raise ValueError(msg)
    return factory(cfg)


def resolve_llm(cfg: LLMConfig, platform: Platform, profile: ResolvedProfile) -> Any:
    """Resolve LLM config to a Pipecat service instance."""
    if cfg.model is None:
        cfg = cfg.model_copy(update={"model": profile.llm_model})

    key = (cfg.provider, platform)
    factory = LLM_REGISTRY.get(key)
    if factory is None:
        msg = f"No LLM service registered for ({cfg.provider!r}, {platform.value!r})"
        raise ValueError(msg)
    return factory(cfg)


def resolve_tts(cfg: TTSConfig, platform: Platform, profile: ResolvedProfile) -> Any:
    """Resolve TTS config to a Pipecat service instance."""
    # Use profile's TTS provider if user didn't override and profile says piper
    effective_provider = cfg.provider
    if cfg.voice is None:
        cfg = cfg.model_copy(
            update={"voice": profile.tts_voice, "provider": profile.tts_provider}
        )
        effective_provider = profile.tts_provider

    key = (effective_provider, platform)
    factory = TTS_REGISTRY.get(key)
    if factory is None:
        msg = f"No TTS service registered for ({effective_provider!r}, {platform.value!r})"
        raise ValueError(msg)
    return factory(cfg)


def resolve_services(
    pipeline_config: PipelineConfig,
    platform: Platform,
    profile: ResolvedProfile,
) -> ResolvedServices:
    """Resolve all pipeline services."""
    return ResolvedServices(
        stt=resolve_stt(pipeline_config.stt, platform, profile),
        llm=resolve_llm(pipeline_config.llm, platform, profile),
        tts=resolve_tts(pipeline_config.tts, platform, profile),
    )
