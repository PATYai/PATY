"""Tests for the ``paty pak ...`` subcommand group."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from paty.cli import cli
from paty.pak.registry import PakRegistry


def _make_pak(parent: Path, name: str = "nova") -> Path:
    d = parent / name
    d.mkdir(parents=True)
    (d / "pak.yaml").write_text(
        textwrap.dedent(f"""\
            pak:
              name: {name}
              version: 0.2.0
              description: "fixture pak"
        """)
    )
    (d / "soul.md").write_text(f"You are {name}.")
    return d


@pytest.fixture
def isolated_paks(tmp_path: Path, monkeypatch):
    """Patch PakRegistry's defaults to point at tmp_path so the CLI doesn't
    touch ``~/.paty/``."""
    user = tmp_path / "user"
    user.mkdir()
    state = tmp_path / "state"

    monkeypatch.setattr(
        "paty.pak.registry._default_paks_dirs",
        lambda: [user],
    )
    monkeypatch.setattr(
        "paty.pak.registry.DEFAULT_ACTIVE_FILE",
        state / "active.txt",
    )
    return user


class TestPakList:
    def test_empty(self, isolated_paks: Path):
        result = CliRunner().invoke(cli, ["pak", "list"])
        assert result.exit_code == 0
        assert "No PAKs found" in result.output

    def test_lists_paks(self, isolated_paks: Path):
        _make_pak(isolated_paks, "nova")
        _make_pak(isolated_paks, "coach")
        result = CliRunner().invoke(cli, ["pak", "list"])
        assert result.exit_code == 0
        assert "nova" in result.output
        assert "coach" in result.output


class TestPakActive:
    def test_unset(self, isolated_paks: Path):
        result = CliRunner().invoke(cli, ["pak", "active"])
        assert result.exit_code == 0
        assert "No PAK selected" in result.output

    def test_after_switch(self, isolated_paks: Path):
        _make_pak(isolated_paks, "nova")
        # Default registry now sees the patched dirs
        reg = PakRegistry()
        reg.set_active("nova")
        result = CliRunner().invoke(cli, ["pak", "active"])
        assert result.exit_code == 0
        assert "nova" in result.output


class TestPakValidate:
    def test_valid(self, tmp_path: Path):
        pak_path = _make_pak(tmp_path, "nova")
        result = CliRunner().invoke(cli, ["pak", "validate", str(pak_path)])
        assert result.exit_code == 0
        assert "nova" in result.output
        assert "v0.2.0" in result.output

    def test_invalid(self, tmp_path: Path):
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "pak.yaml").write_text("pak: {}\n")  # missing required name
        # soul.md absent — but schema fails first
        result = CliRunner().invoke(cli, ["pak", "validate", str(bad)])
        assert result.exit_code == 1
        assert "Invalid PAK" in result.output


class TestPakSwitch:
    def test_switch_to_existing(self, isolated_paks: Path):
        _make_pak(isolated_paks, "nova")
        result = CliRunner().invoke(cli, ["pak", "switch", "nova"])
        assert result.exit_code == 0
        assert "nova" in result.output

        reg = PakRegistry()
        assert reg.active_name() == "nova"

    def test_switch_to_missing_fails(self, isolated_paks: Path):
        result = CliRunner().invoke(cli, ["pak", "switch", "ghost"])
        assert result.exit_code == 1
        assert "Cannot switch" in result.output

        reg = PakRegistry()
        assert reg.active_name() is None
