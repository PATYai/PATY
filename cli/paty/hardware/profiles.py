"""Hardware profiles — named presets mapping to model/voice defaults."""

from __future__ import annotations

from dataclasses import dataclass

from paty.config.schema import HardwareConfig, HardwareProfile, Platform
from paty.hardware.detect import HardwareInfo


@dataclass
class ResolvedProfile:
    name: str
    stt_provider: str
    stt_model: str
    llm_model: str
    tts_provider: str
    tts_voice: str

    # STT tuning (only used by faster_whisper backend)
    stt_compute_type: str = "default"

    # LLM server tuning (mlx_lm / llama.cpp flags)
    llm_max_tokens: int = 512
    llm_prompt_cache_size: int = 4
    llm_prefill_step_size: int = 2048

    # Memory wiring (fraction of max_recommended_working_set_size)
    wire_fraction: float = 0.0


PROFILES: dict[HardwareProfile, ResolvedProfile] = {
    HardwareProfile.APPLE_16GB: ResolvedProfile(
        name="apple-16gb",
        stt_provider="mlx-audio",
        stt_model="UsefulSensors/moonshine-base",
        llm_model="qwen3:4b",
        tts_provider="kokoro",
        tts_voice="af_bella",
        # Tight memory budget: small cache, short generations, small prefill
        llm_max_tokens=256,
        llm_prompt_cache_size=1,
        llm_prefill_step_size=512,
        # Wire 75% of recommended working set for in-process models
        wire_fraction=0.75,
    ),
    HardwareProfile.APPLE_24GB: ResolvedProfile(
        name="apple-24gb",
        stt_provider="mlx-audio",
        stt_model="UsefulSensors/moonshine-base",
        llm_model="qwen3:14b",
        tts_provider="kokoro",
        tts_voice="af_bella",
        llm_max_tokens=512,
        llm_prompt_cache_size=2,
        llm_prefill_step_size=1024,
        wire_fraction=0.5,
    ),
    HardwareProfile.CUDA_24GB: ResolvedProfile(
        name="cuda-24gb",
        stt_provider="whisper",
        stt_model="distil-large-v2",
        llm_model="qwen3:14b",
        tts_provider="kokoro",
        tts_voice="af_bella",
        # CUDA supports float16 natively
        stt_compute_type="float16",
    ),
    HardwareProfile.CPU_ONLY: ResolvedProfile(
        name="cpu-only",
        stt_provider="whisper",
        stt_model="distil-medium.en",
        llm_model="qwen3:4b",
        tts_provider="piper",
        tts_voice="en_US-ryan-high",
        stt_compute_type="int8",
        llm_max_tokens=256,
        llm_prompt_cache_size=1,
        llm_prefill_step_size=512,
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
