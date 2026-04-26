"""Load and validate a PAK from a directory on disk."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML, YAMLError

from paty.pak.schema import PakManifest

# Filenames discovered automatically inside ``<pak>/avatar/``.  Each maps
# to an ``AgentState`` value (see paty.bus.events.AgentState).  Missing or
# empty files are silently skipped — PAK authors only ship the states
# they want to override.
AVATAR_STATES = ("idle", "listening", "thinking", "speaking")


class PakLoadError(Exception):
    """Raised when a PAK directory cannot be loaded or validated."""


@dataclass(frozen=True)
class Pak:
    """A loaded, validated PAK: manifest + persona text + avatar + source dir.

    ``avatar`` maps agent-state names (``idle``, ``listening``, ``thinking``,
    ``speaking``) to the text content of ``avatar/<state>.txt``.  States
    without a file are simply absent from the dict; the renderer falls
    back to its built-in defaults for those.
    """

    manifest: PakManifest
    soul: str
    path: Path
    avatar: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.manifest.pak.name


def _load_avatar(pak_dir: Path) -> dict[str, str]:
    """Pick up ``avatar/<state>.txt`` files; return a state→content dict."""
    avatar_dir = pak_dir / "avatar"
    if not avatar_dir.is_dir():
        return {}
    found: dict[str, str] = {}
    for state in AVATAR_STATES:
        f = avatar_dir / f"{state}.txt"
        if not f.is_file():
            continue
        text = f.read_text().rstrip("\n")
        if text.strip():
            found[state] = text
    return found


def load_pak(path: str | Path) -> Pak:
    """Load a PAK directory and return a validated ``Pak``.

    Raises ``PakLoadError`` if the directory does not exist, ``pak.yaml`` is
    missing/empty/invalid, or the soul file is missing/empty.
    """
    path = Path(path)
    if not path.is_dir():
        msg = f"PAK path is not a directory: {path}"
        raise PakLoadError(msg)

    manifest_path = path / "pak.yaml"
    if not manifest_path.is_file():
        msg = f"Missing pak.yaml in {path}"
        raise PakLoadError(msg)

    yaml = YAML()
    try:
        with open(manifest_path) as f:
            raw = yaml.load(f)
    except YAMLError as e:
        msg = f"Invalid YAML in {manifest_path}: {e}"
        raise PakLoadError(msg) from e

    if raw is None:
        msg = f"pak.yaml is empty: {manifest_path}"
        raise PakLoadError(msg)

    try:
        manifest = PakManifest.model_validate(raw)
    except ValidationError as e:
        msg = f"Invalid pak.yaml at {manifest_path}: {e}"
        raise PakLoadError(msg) from e

    soul_path = path / manifest.pak.soul
    if not soul_path.is_file():
        msg = f"Missing soul file {manifest.pak.soul!r} in {path}"
        raise PakLoadError(msg)

    soul_text = soul_path.read_text().strip()
    if not soul_text:
        msg = f"Soul file is empty: {soul_path}"
        raise PakLoadError(msg)

    avatar = _load_avatar(path)

    return Pak(manifest=manifest, soul=soul_text, path=path, avatar=avatar)
