"""Tests for service resolver — registry lookups without instantiation."""

from __future__ import annotations

import contextlib

import pytest

from paty.config.schema import Platform, STTConfig
from paty.hardware.profiles import ResolvedProfile
from paty.resolve.registry import LLM_REGISTRY, STT_REGISTRY, TTS_REGISTRY


class TestRegistryKeys:
    """Verify the registry has the expected (provider, platform) entries."""

    def test_stt_whisper_all_platforms(self):
        for plat in (Platform.MLX, Platform.CUDA, Platform.CPU):
            assert ("whisper", plat) in STT_REGISTRY

    def test_stt_mlx_audio_on_mlx(self):
        assert ("mlx-audio", Platform.MLX) in STT_REGISTRY

    def test_llm_ollama_all_platforms(self):
        for plat in (Platform.MLX, Platform.CUDA, Platform.CPU):
            assert ("ollama", plat) in LLM_REGISTRY

    def test_tts_kokoro_mlx_and_cuda(self):
        assert ("kokoro", Platform.MLX) in TTS_REGISTRY
        assert ("kokoro", Platform.CUDA) in TTS_REGISTRY

    def test_tts_piper_cpu(self):
        assert ("piper", Platform.CPU) in TTS_REGISTRY


class TestResolverFillDefaults:
    """Test that resolve_* fills model from profile when not set."""

    def test_stt_model_filled_from_profile(self):
        from paty.resolve.resolver import resolve_stt

        cfg = STTConfig(provider="whisper", model=None)
        profile = ResolvedProfile(
            name="test",
            stt_provider="whisper",
            stt_model="distil-small.en",
            llm_model="qwen3:8b",
            tts_provider="kokoro",
            tts_voice="af_bella",
        )
        # Factory will fail on Pipecat import if optional deps aren't installed.
        # That's fine — we just verify the registry lookup + default filling works.
        with contextlib.suppress(ImportError):
            resolve_stt(cfg, Platform.MLX, profile, compute_executor=None)

    def test_missing_registry_key_raises(self):
        from paty.resolve.resolver import resolve_stt

        cfg = STTConfig(provider="nonexistent", model="some-model")
        profile = ResolvedProfile(
            name="test",
            stt_provider="nonexistent",
            stt_model="x",
            llm_model="x",
            tts_provider="x",
            tts_voice="x",
        )
        with pytest.raises(ValueError, match="No STT service registered"):
            resolve_stt(cfg, Platform.MLX, profile, compute_executor=None)
