"""Tests for the PAK manifest schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paty.pak.schema import (
    PakConversationConfig,
    PakLLMConfig,
    PakManifest,
    PakTTSConfig,
    PakVoiceConfig,
)


class TestPakTTSConfig:
    def test_defaults(self):
        cfg = PakTTSConfig()
        assert cfg.provider == "kokoro"
        assert cfg.voice is None

    def test_explicit(self):
        cfg = PakTTSConfig(provider="piper", voice="en_US-ryan-high")
        assert cfg.provider == "piper"
        assert cfg.voice == "en_US-ryan-high"


class TestPakLLMConfig:
    def test_default_is_inherit(self):
        assert PakLLMConfig().model is None

    def test_explicit_pin(self):
        cfg = PakLLMConfig(model="qwen3:8b")
        assert cfg.model == "qwen3:8b"


class TestPakConversationConfig:
    def test_defaults(self):
        cfg = PakConversationConfig()
        assert cfg.retention_days == 30
        assert cfg.max_turns_loaded == 50


class TestPakManifest:
    def test_minimal(self):
        m = PakManifest.model_validate({"pak": {"name": "nova"}})
        assert m.pak.name == "nova"
        assert m.pak.version == "0.0.1"
        assert m.pak.soul == "soul.md"
        assert isinstance(m.voice, PakVoiceConfig)
        assert m.voice.tts.provider == "kokoro"

    def test_full(self):
        data = {
            "pak": {
                "name": "nova",
                "version": "0.2.0",
                "description": "curious sci-fi companion",
                "soul": "soul.md",
            },
            "voice": {
                "tts": {"provider": "kokoro", "voice": "af_nova"},
                "llm": {"model": "qwen3:8b"},
            },
            "conversation": {"retention_days": 7, "max_turns_loaded": 25},
        }
        m = PakManifest.model_validate(data)
        assert m.pak.version == "0.2.0"
        assert m.voice.tts.voice == "af_nova"
        assert m.voice.llm.model == "qwen3:8b"
        assert m.conversation.retention_days == 7

    def test_missing_pak_block_raises(self):
        with pytest.raises(ValidationError):
            PakManifest.model_validate({})

    def test_missing_pak_name_raises(self):
        with pytest.raises(ValidationError):
            PakManifest.model_validate({"pak": {}})

    def test_heartbeats_field_is_ignored_for_now(self):
        """The heartbeats field is reserved for a follow-up MR; until then,
        unknown top-level keys must not crash the manifest load (Pydantic's
        default behavior, but worth pinning down)."""
        m = PakManifest.model_validate(
            {"pak": {"name": "nova"}, "heartbeats": {"enabled": True}}
        )
        assert m.pak.name == "nova"
