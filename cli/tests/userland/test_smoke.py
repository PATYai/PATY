"""End-to-end smoke tests against the installed `paty` binary.

These run in two contexts:
- on-merge (push to main): wheel built from source, installed into a clean
  venv with no extras. Selector: `-m "userland and merge"`.
- post-publish (after PyPI release): `paty==<tag>` installed from PyPI into
  a clean venv with no extras. Selector: `-m userland` (full set).

Tests subprocess the actual `paty` console script — they verify the shipped
package, not in-tree modules. Excluded from default pytest runs via
`addopts = --ignore=tests/userland` in cli/pyproject.toml.
"""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

# Resolve `paty` next to the running Python so the tests work whether or not
# the venv's bin/ is on PATH (CI runners typically don't activate the venv).
PATY_BIN = str(Path(sys.executable).parent / "paty")

# Read the version of the *installed* paty distribution, not whatever an
# `import paty` would resolve to. In post-publish CI pytest's cwd happens to
# be the source tree, which can shadow the installed package.
INSTALLED_VERSION = version("paty")


def _paty(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PATY_BIN, *args], capture_output=True, text=True, check=False
    )


@pytest.mark.userland
@pytest.mark.merge
def test_version_matches_dist():
    r = _paty("--version")
    assert r.returncode == 0, r.stderr
    assert INSTALLED_VERSION in r.stdout


@pytest.mark.userland
@pytest.mark.merge
def test_help_lists_core_commands():
    r = _paty("--help")
    assert r.returncode == 0
    for cmd in ("run", "bus", "pak", "profiles"):
        assert cmd in r.stdout, f"missing command in --help: {cmd}"


@pytest.mark.userland
@pytest.mark.merge
def test_pipeline_modules_import():
    """Smoke-import the heavy modules `paty run` lazily pulls in.

    Catches ABI/API breaks in pinned upstream deps (e.g. pipecat) that none
    of the introspection commands above would surface, since the no-backend
    gate exits before `_run()` reaches these imports.
    """
    code = (
        "import paty.pipeline.builder, "
        "paty.resolve.registry, "
        "paty.runtime.manager, "
        "paty.runtime.stt_service, "
        "paty.runtime.tts_service"
    )
    r = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, r.stderr


@pytest.mark.userland
@pytest.mark.merge
def test_bundled_pak_listed():
    r = _paty("pak", "list")
    assert r.returncode == 0
    assert "paty" in r.stdout


@pytest.mark.userland
def test_profiles_exits_clean():
    r = _paty("profiles")
    assert r.returncode == 0


@pytest.mark.userland
def test_pak_validate_bundled():
    """Validate the bundled PAK at its installed location."""
    import paty

    bundled = Path(paty.__file__).parent / "paks" / "paty"
    r = _paty("pak", "validate", str(bundled))
    assert r.returncode == 0, r.stderr
    assert "paty" in r.stdout


@pytest.mark.userland
def test_run_without_backend_prints_install_hint(tmp_path: Path):
    """With no backend installed, `paty run` should bail with the 3-line install hint."""
    cfg = tmp_path / "test.yaml"
    cfg.write_text("agent:\n  name: test\n  persona: test persona\n")
    r = _paty("run", str(cfg))
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "uv tool install 'paty[mlx]'" in out
    assert "uv tool install 'paty[cuda]'" in out
    assert "uv tool install 'paty[cpu]'" in out
