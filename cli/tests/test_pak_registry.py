"""Tests for the PAK registry: discovery, shadowing, and the active pointer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from paty.pak.loader import PakLoadError
from paty.pak.registry import PakRegistry, bundled_paks_dir


def _make_pak(parent: Path, name: str, soul: str = "You are X.") -> Path:
    d = parent / name
    d.mkdir(parents=True)
    (d / "pak.yaml").write_text(
        textwrap.dedent(f"""\
            pak:
              name: {name}
              version: 0.1.0
        """)
    )
    (d / "soul.md").write_text(soul)
    return d


@pytest.fixture
def isolated_registry(tmp_path: Path) -> PakRegistry:
    user = tmp_path / "user"
    bundled = tmp_path / "bundled"
    user.mkdir()
    bundled.mkdir()
    return PakRegistry(
        paks_dirs=[user, bundled],
        active_file=tmp_path / "state" / "active.txt",
    )


class TestList:
    def test_empty(self, isolated_registry: PakRegistry):
        assert isolated_registry.list() == []

    def test_lists_user_and_bundled(self, isolated_registry: PakRegistry):
        user, bundled = isolated_registry.paks_dirs
        _make_pak(user, "nova")
        _make_pak(bundled, "paty")
        assert isolated_registry.list() == ["nova", "paty"]

    def test_user_shadows_bundled(self, isolated_registry: PakRegistry):
        user, bundled = isolated_registry.paks_dirs
        _make_pak(user, "paty", soul="user-overridden paty")
        _make_pak(bundled, "paty", soul="bundled paty")
        assert isolated_registry.list() == ["paty"]
        loaded = isolated_registry.get("paty")
        assert loaded.soul == "user-overridden paty"

    def test_skips_non_directories(
        self, isolated_registry: PakRegistry, tmp_path: Path
    ):
        user = isolated_registry.paks_dirs[0]
        _make_pak(user, "nova")
        (user / "stray-file.txt").write_text("hi")
        assert isolated_registry.list() == ["nova"]

    def test_skips_dirs_without_pak_yaml(self, isolated_registry: PakRegistry):
        user = isolated_registry.paks_dirs[0]
        _make_pak(user, "nova")
        (user / "not-a-pak").mkdir()
        assert isolated_registry.list() == ["nova"]

    def test_missing_dirs_are_ignored(self, tmp_path: Path):
        reg = PakRegistry(
            paks_dirs=[tmp_path / "nope", tmp_path / "still-nope"],
            active_file=tmp_path / "active.txt",
        )
        assert reg.list() == []


class TestGet:
    def test_returns_loaded_pak(self, isolated_registry: PakRegistry):
        user = isolated_registry.paks_dirs[0]
        _make_pak(user, "nova")
        loaded = isolated_registry.get("nova")
        assert loaded.name == "nova"

    def test_searches_in_order(self, isolated_registry: PakRegistry):
        _user, bundled = isolated_registry.paks_dirs
        _make_pak(bundled, "nova", soul="bundled")
        loaded = isolated_registry.get("nova")
        assert loaded.soul == "bundled"

    def test_missing_pak_raises(self, isolated_registry: PakRegistry):
        with pytest.raises(PakLoadError, match="PAK not found"):
            isolated_registry.get("ghost")


class TestActivePointer:
    def test_unset_returns_none(self, isolated_registry: PakRegistry):
        assert isolated_registry.active_name() is None
        assert isolated_registry.active() is None

    def test_set_and_read(self, isolated_registry: PakRegistry):
        user = isolated_registry.paks_dirs[0]
        _make_pak(user, "nova")
        isolated_registry.set_active("nova")
        assert isolated_registry.active_name() == "nova"
        loaded = isolated_registry.active()
        assert loaded is not None
        assert loaded.name == "nova"

    def test_set_active_creates_state_dir(self, isolated_registry: PakRegistry):
        user = isolated_registry.paks_dirs[0]
        _make_pak(user, "nova")
        assert not isolated_registry.active_file.parent.exists()
        isolated_registry.set_active("nova")
        assert isolated_registry.active_file.is_file()

    def test_set_active_validates_pak_exists(self, isolated_registry: PakRegistry):
        with pytest.raises(PakLoadError):
            isolated_registry.set_active("ghost")
        assert isolated_registry.active_name() is None

    def test_whitespace_only_active_file_is_unset(self, isolated_registry: PakRegistry):
        isolated_registry.active_file.parent.mkdir(parents=True)
        isolated_registry.active_file.write_text("   \n")
        assert isolated_registry.active_name() is None


class TestBundledDefault:
    """The shipped paty PAK must be loadable through the default registry —
    out-of-box ``paty run`` depends on this.
    """

    def test_bundled_paty_is_discoverable(self):
        reg = PakRegistry(paks_dirs=[bundled_paks_dir()], active_file=Path("/tmp/x"))
        assert "paty" in reg.list()
        loaded = reg.get("paty")
        assert loaded.name == "paty"
        assert loaded.soul  # non-empty
