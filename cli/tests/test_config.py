"""Tests for config schema and loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from paty.config.loader import load_config
from paty.config.schema import (
    PakConfig,
    PatyConfig,
    PipelineConfig,
)


class TestPipelineConfigNormalization:
    def test_string_shorthand(self):
        data = {"stt": "whisper", "llm": "ollama", "tts": "kokoro"}
        cfg = PipelineConfig.model_validate(data)
        assert cfg.stt.provider == "whisper"
        assert cfg.llm.provider == "ollama"
        assert cfg.tts.provider == "kokoro"

    def test_dict_form(self):
        data = {
            "stt": {"provider": "whisper", "model": "large-v3-turbo"},
            "llm": {"provider": "ollama", "model": "qwen3:14b"},
            "tts": {"provider": "kokoro", "voice": "af_bella"},
        }
        cfg = PipelineConfig.model_validate(data)
        assert cfg.stt.model == "large-v3-turbo"
        assert cfg.llm.model == "qwen3:14b"
        assert cfg.tts.voice == "af_bella"

    def test_defaults(self):
        cfg = PipelineConfig()
        assert cfg.stt.provider == "whisper"
        assert cfg.llm.provider == "ollama"
        assert cfg.tts.provider == "kokoro"
        assert cfg.vad == "silero"


class TestPatyConfig:
    def test_minimal_config(self):
        data = {
            "agent": {"name": "test", "persona": "You are a test agent."},
        }
        cfg = PatyConfig.model_validate(data)
        assert cfg.agent.name == "test"
        assert cfg.pipeline.stt.provider == "whisper"
        assert cfg.hardware.profile.value == "auto"
        assert cfg.tracing.enabled is True

    def test_empty_config_is_valid(self):
        """An empty config is allowed — the runtime will fall back to the
        bundled default PAK."""
        cfg = PatyConfig.model_validate({})
        assert cfg.agent is None
        assert cfg.pak.active is None

    def test_pak_only(self):
        cfg = PatyConfig.model_validate({"pak": {"active": "nova"}})
        assert cfg.agent is None
        assert cfg.pak.active == "nova"

    def test_agent_and_pak_are_mutually_exclusive(self):
        with pytest.raises(ValidationError, match="not both"):
            PatyConfig.model_validate(
                {
                    "agent": {"name": "x", "persona": "x"},
                    "pak": {"active": "nova"},
                }
            )

    def test_pak_block_defaults(self):
        assert PakConfig().active is None
        assert PakConfig().paks_dir is None

    def test_full_config(self):
        data = {
            "agent": {"name": "front-desk", "persona": "You are a receptionist."},
            "pipeline": {
                "stt": {"provider": "whisper", "model": "large-v3-turbo"},
                "llm": {"provider": "ollama", "model": "qwen3:8b"},
                "tts": "kokoro",
                "vad": "silero",
            },
            "hardware": {"profile": "apple-24gb"},
            "sip": {"host": "sip.example.com", "username": "100"},
            "tracing": {"enabled": True, "console": False},
        }
        cfg = PatyConfig.model_validate(data)
        assert cfg.agent.name == "front-desk"
        assert cfg.pipeline.stt.model == "large-v3-turbo"
        assert cfg.pipeline.tts.provider == "kokoro"
        assert cfg.hardware.profile.value == "apple-24gb"


class TestLoader:
    def test_load_yaml(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            agent:
              name: test-bot
              persona: "You are a test bot."
            pipeline:
              stt: whisper
              llm: ollama
              tts: kokoro
        """)
        config_file = tmp_path / "paty.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert cfg.agent.name == "test-bot"
        assert cfg.pipeline.stt.provider == "whisper"

    def test_env_interpolation(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TEST_SIP_PASS", "secret123")
        yaml_content = textwrap.dedent("""\
            agent:
              name: test-bot
              persona: "Test."
            sip:
              password: "${TEST_SIP_PASS}"
        """)
        config_file = tmp_path / "paty.yaml"
        config_file.write_text(yaml_content)

        cfg = load_config(config_file)
        assert cfg.sip.password == "secret123"

    def test_missing_env_var_raises(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            agent:
              name: test-bot
              persona: "Test."
            sip:
              password: "${DEFINITELY_NOT_SET_12345}"
        """)
        config_file = tmp_path / "paty.yaml"
        config_file.write_text(yaml_content)

        with pytest.raises(ValueError, match="DEFINITELY_NOT_SET_12345"):
            load_config(config_file)

    def test_empty_file_raises(self, tmp_path: Path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        with pytest.raises(ValueError, match="empty"):
            load_config(config_file)
