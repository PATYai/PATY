"""Tests for the PAK → PatyConfig runtime bridge."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from paty.config.schema import (
    LLMConfig,
    PakConfig,
    PatyConfig,
    PipelineConfig,
    TTSConfig,
)
from paty.pak.registry import PakRegistry
from paty.pak.runtime import (
    apply_pak_voice,
    resolve_persona,
    warn_if_llm_pin_off_profile,
)


def _make_pak(
    parent: Path,
    name: str = "nova",
    *,
    tts_voice: str | None = "af_nova",
    llm_pin: str | None = None,
) -> Path:
    d = parent / name
    d.mkdir(parents=True)
    voice_block = "voice:\n"
    voice_block += "  tts:\n    provider: kokoro\n"
    if tts_voice is not None:
        voice_block += f"    voice: {tts_voice}\n"
    if llm_pin is not None:
        voice_block += f"  llm:\n    model: {llm_pin}\n"
    (d / "pak.yaml").write_text(
        textwrap.dedent(f"""\
            pak:
              name: {name}
        """)
        + voice_block
    )
    (d / "soul.md").write_text(f"You are {name}.")
    return d


@pytest.fixture
def isolated_registry(tmp_path: Path) -> PakRegistry:
    user = tmp_path / "user"
    user.mkdir()
    return PakRegistry(
        paks_dirs=[user],
        active_file=tmp_path / "state" / "active.txt",
    )


class TestResolvePersona:
    def test_inline_persona_synthesizes_transient_pak(
        self, isolated_registry: PakRegistry
    ):
        cfg = PatyConfig(pak=PakConfig(persona="hi there"))
        resolved = resolve_persona(cfg, registry=isolated_registry)
        assert resolved.persona == "hi there"
        assert resolved.pak is not None
        assert resolved.pak.name == "inline"
        assert resolved.pak.soul == "hi there"

    def test_named_pak(self, isolated_registry: PakRegistry):
        _make_pak(isolated_registry.paks_dirs[0], "nova")
        cfg = PatyConfig(pak=PakConfig(active="nova"))
        resolved = resolve_persona(cfg, registry=isolated_registry)
        assert resolved.persona == "You are nova."
        assert resolved.pak is not None
        assert resolved.pak.name == "nova"

    def test_falls_back_to_default_paty_pak(self, isolated_registry: PakRegistry):
        _make_pak(isolated_registry.paks_dirs[0], "paty", tts_voice="af_bella")
        cfg = PatyConfig()  # no pak.persona, no pak.active, no active.txt
        resolved = resolve_persona(cfg, registry=isolated_registry)
        assert resolved.pak is not None
        assert resolved.pak.name == "paty"

    def test_uses_active_txt_when_config_unspecified(
        self, isolated_registry: PakRegistry
    ):
        """`paty pak switch nova` writes active.txt; `paty run` must honor it."""
        _make_pak(isolated_registry.paks_dirs[0], "nova", tts_voice="af_sky")
        isolated_registry.set_active("nova")
        cfg = PatyConfig()  # no pak.active in YAML
        resolved = resolve_persona(cfg, registry=isolated_registry)
        assert resolved.pak.name == "nova"

    def test_config_pak_active_outranks_active_txt(
        self, isolated_registry: PakRegistry
    ):
        _make_pak(isolated_registry.paks_dirs[0], "nova")
        _make_pak(isolated_registry.paks_dirs[0], "coach")
        isolated_registry.set_active("nova")
        cfg = PatyConfig(pak=PakConfig(active="coach"))
        resolved = resolve_persona(cfg, registry=isolated_registry)
        assert resolved.pak.name == "coach"


class TestApplyPakVoice:
    def test_applies_when_user_has_no_overrides(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak_path = _make_pak(tmp_path, "nova", tts_voice="af_nova")
        pak = load_pak(pak_path)

        cfg = PatyConfig()
        new_cfg = apply_pak_voice(cfg, pak)
        assert new_cfg.pipeline.tts.voice == "af_nova"
        assert new_cfg.pipeline.tts.provider == "kokoro"

    def test_user_voice_override_wins(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak_path = _make_pak(tmp_path, "nova", tts_voice="af_nova")
        pak = load_pak(pak_path)

        cfg = PatyConfig(
            pipeline=PipelineConfig(
                tts=TTSConfig(provider="piper", voice="en_US-ryan-high")
            )
        )
        new_cfg = apply_pak_voice(cfg, pak)
        assert new_cfg.pipeline.tts.voice == "en_US-ryan-high"
        assert new_cfg.pipeline.tts.provider == "piper"

    def test_pak_without_voice_leaves_config_untouched(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak_path = _make_pak(tmp_path, "nova", tts_voice=None)
        pak = load_pak(pak_path)

        cfg = PatyConfig()
        new_cfg = apply_pak_voice(cfg, pak)
        assert new_cfg.pipeline.tts.voice is None

    def test_pak_llm_pin_applied_when_no_user_override(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak_path = _make_pak(tmp_path, "nova", llm_pin="qwen3:8b")
        pak = load_pak(pak_path)

        cfg = PatyConfig()
        new_cfg = apply_pak_voice(cfg, pak)
        assert new_cfg.pipeline.llm.model == "qwen3:8b"

    def test_user_llm_override_wins(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak_path = _make_pak(tmp_path, "nova", llm_pin="qwen3:8b")
        pak = load_pak(pak_path)

        cfg = PatyConfig(pipeline=PipelineConfig(llm=LLMConfig(model="qwen3:14b")))
        new_cfg = apply_pak_voice(cfg, pak)
        assert new_cfg.pipeline.llm.model == "qwen3:14b"

    def test_returns_new_object(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak_path = _make_pak(tmp_path, "nova", tts_voice="af_nova")
        pak = load_pak(pak_path)

        cfg = PatyConfig()
        new_cfg = apply_pak_voice(cfg, pak)
        assert new_cfg is not cfg
        assert cfg.pipeline.tts.voice is None  # original untouched


class TestWarnIfLlmPinOffProfile:
    def test_no_pin_no_warning(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak = load_pak(_make_pak(tmp_path, "nova", llm_pin=None))
        assert warn_if_llm_pin_off_profile(pak, "qwen3:4b") is None

    def test_pin_matches_profile_no_warning(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak = load_pak(_make_pak(tmp_path, "nova", llm_pin="qwen3:4b"))
        assert warn_if_llm_pin_off_profile(pak, "qwen3:4b") is None

    def test_pin_disagrees_warns(self, tmp_path: Path):
        from paty.pak.loader import load_pak

        pak = load_pak(_make_pak(tmp_path, "nova", llm_pin="qwen3:8b"))
        msg = warn_if_llm_pin_off_profile(pak, "qwen3:4b")
        assert msg is not None
        assert "qwen3:8b" in msg
        assert "qwen3:4b" in msg
        assert "nova" in msg
