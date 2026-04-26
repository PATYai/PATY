"""Tests for the PAK directory loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from paty.pak.loader import Pak, PakLoadError, load_pak


def _write_pak(
    base: Path,
    name: str = "nova",
    *,
    manifest: str | None = None,
    soul_text: str | None = "You are Nova.",
    soul_filename: str = "soul.md",
) -> Path:
    """Create a fixture PAK at ``base/name`` and return its path."""
    pak_dir = base / name
    pak_dir.mkdir(parents=True)
    if manifest is None:
        manifest = textwrap.dedent(f"""\
            pak:
              name: {name}
            voice:
              tts:
                provider: kokoro
                voice: af_nova
        """)
    (pak_dir / "pak.yaml").write_text(manifest)
    if soul_text is not None:
        (pak_dir / soul_filename).write_text(soul_text)
    return pak_dir


class TestLoadPakHappy:
    def test_loads_directory(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path)
        loaded = load_pak(pak_path)
        assert isinstance(loaded, Pak)
        assert loaded.name == "nova"
        assert loaded.soul == "You are Nova."
        assert loaded.path == pak_path
        assert loaded.manifest.voice.tts.voice == "af_nova"

    def test_strips_soul_whitespace(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path, soul_text="\n\n  hello  \n\n")
        loaded = load_pak(pak_path)
        assert loaded.soul == "hello"

    def test_custom_soul_filename(self, tmp_path: Path):
        manifest = textwrap.dedent("""\
            pak:
              name: nova
              soul: persona.md
        """)
        pak_path = _write_pak(tmp_path, manifest=manifest, soul_filename="persona.md")
        loaded = load_pak(pak_path)
        assert loaded.soul == "You are Nova."

    def test_pak_is_frozen(self, tmp_path: Path):
        from dataclasses import FrozenInstanceError

        pak_path = _write_pak(tmp_path)
        loaded = load_pak(pak_path)
        with pytest.raises(FrozenInstanceError):
            loaded.soul = "tampered"  # type: ignore[misc]


class TestLoadAvatar:
    def test_no_avatar_dir_yields_empty_dict(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path)
        loaded = load_pak(pak_path)
        assert loaded.avatar == {}

    def test_picks_up_state_files(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path)
        avatar = pak_path / "avatar"
        avatar.mkdir()
        (avatar / "idle.txt").write_text("(•◡•)\n")
        (avatar / "speaking.txt").write_text("(•o•)\n")
        loaded = load_pak(pak_path)
        assert loaded.avatar == {"idle": "(•◡•)", "speaking": "(•o•)"}

    def test_supports_multiline_art(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path)
        avatar = pak_path / "avatar"
        avatar.mkdir()
        (avatar / "idle.txt").write_text(" .---.\n( o o )\n '---'\n")
        loaded = load_pak(pak_path)
        assert loaded.avatar["idle"] == " .---.\n( o o )\n '---'"

    def test_skips_empty_files(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path)
        avatar = pak_path / "avatar"
        avatar.mkdir()
        (avatar / "idle.txt").write_text("(•◡•)\n")
        (avatar / "thinking.txt").write_text("\n  \n")
        loaded = load_pak(pak_path)
        assert "idle" in loaded.avatar
        assert "thinking" not in loaded.avatar

    def test_unknown_state_files_ignored(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path)
        avatar = pak_path / "avatar"
        avatar.mkdir()
        (avatar / "idle.txt").write_text("(•◡•)")
        (avatar / "dancing.txt").write_text("(•_•)")  # not a known state
        loaded = load_pak(pak_path)
        assert set(loaded.avatar.keys()) == {"idle"}


class TestLoadPakErrors:
    def test_missing_directory(self, tmp_path: Path):
        with pytest.raises(PakLoadError, match="not a directory"):
            load_pak(tmp_path / "does_not_exist")

    def test_path_is_a_file(self, tmp_path: Path):
        f = tmp_path / "not_a_dir"
        f.write_text("hi")
        with pytest.raises(PakLoadError, match="not a directory"):
            load_pak(f)

    def test_missing_pak_yaml(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(PakLoadError, match=r"Missing pak\.yaml"):
            load_pak(empty)

    def test_empty_pak_yaml(self, tmp_path: Path):
        d = tmp_path / "nova"
        d.mkdir()
        (d / "pak.yaml").write_text("")
        with pytest.raises(PakLoadError, match="empty"):
            load_pak(d)

    def test_invalid_yaml(self, tmp_path: Path):
        d = tmp_path / "nova"
        d.mkdir()
        (d / "pak.yaml").write_text("pak: { name: nova\n")  # unclosed
        with pytest.raises(PakLoadError, match="Invalid YAML"):
            load_pak(d)

    def test_invalid_manifest_schema(self, tmp_path: Path):
        d = tmp_path / "nova"
        d.mkdir()
        (d / "pak.yaml").write_text("pak: {}\n")  # missing required name
        with pytest.raises(PakLoadError, match=r"Invalid pak\.yaml"):
            load_pak(d)

    def test_missing_soul_file(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path, soul_text=None)
        with pytest.raises(PakLoadError, match="Missing soul file"):
            load_pak(pak_path)

    def test_empty_soul_file(self, tmp_path: Path):
        pak_path = _write_pak(tmp_path, soul_text="   \n  \n")
        with pytest.raises(PakLoadError, match="Soul file is empty"):
            load_pak(pak_path)
