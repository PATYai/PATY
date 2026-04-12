"""Hardware profiles — named presets mapping to model/voice defaults."""

from __future__ import annotations

from dataclasses import dataclass

from paty.config.schema import HardwareConfig, HardwareProfile, Platform
from paty.hardware.detect import HardwareInfo


@dataclass
class ResolvedProfile:
    name: str
    stt_model: str
    llm_model: str
    tts_provider: str
    tts_voice: str


PROFILES: dict[HardwareProfile, ResolvedProfile] = {
    HardwareProfile.APPLE_16GB: ResolvedProfile(
        name="apple-16gb",
        stt_model="distil-large-v3",
        llm_model="qwen3:8b",
        tts_provider="kokoro",
        tts_voice="af_bella",
    ),
    HardwareProfile.APPLE_24GB: ResolvedProfile(
        name="apple-24gb",
        stt_model="large-v3-turbo",
        llm_model="qwen3:14b",
        tts_provider="kokoro",
        tts_voice="af_bella",
    ),
    HardwareProfile.CUDA_24GB: ResolvedProfile(
        name="cuda-24gb",
        stt_model="distil-large-v2",
        llm_model="qwen3:14b",
        tts_provider="kokoro",
        tts_voice="af_bella",
    ),
    HardwareProfile.CPU_ONLY: ResolvedProfile(
        name="cpu-only",
        stt_model="distil-medium.en",
        llm_model="qwen3:4b",
        tts_provider="piper",
        tts_voice="en_US-ryan-high",
    ),
}


def _auto_select_profile(
    hw: HardwareInfo,
) -> HardwareProfile | None:
    """Pick the best profile based on detected platform + memory."""
    if hw.platform == Platform.MLX:
        if hw.memory_mb >= 20_000:
            return HardwareProfile.APPLE_24GB
        return HardwareProfile.APPLE_16GB

    if hw.platform == Platform.CUDA:
        return HardwareProfile.CUDA_24GB

    return HardwareProfile.CPU_ONLY


def resolve_profile(
    hw_config: HardwareConfig, hw_info: HardwareInfo
) -> ResolvedProfile:
    """Resolve a HardwareConfig to a concrete profile with model defaults."""
    profile_key = hw_config.profile
    if profile_key == HardwareProfile.AUTO:
        profile_key = _auto_select_profile(hw_info)

    return PROFILES[profile_key]
