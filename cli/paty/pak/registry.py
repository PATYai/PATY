"""Discover installed PAKs and read/write the active pointer.

Search order is *user-installed first, bundled second*: a PAK named ``paty``
in ``~/.paty/paks/`` shadows the bundled default.  This lets a user
override or fork the built-in PAK without touching the install.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from paty.pak.loader import Pak, PakLoadError, load_pak

DEFAULT_USER_PAKS_DIR = Path.home() / ".paty" / "paks"
DEFAULT_ACTIVE_FILE = Path.home() / ".paty" / "state" / "active.txt"


def bundled_paks_dir() -> Path:
    """Path to PAKs that ship inside the installed package."""
    return Path(str(files("paty").joinpath("paks")))


def _default_paks_dirs() -> list[Path]:
    return [DEFAULT_USER_PAKS_DIR, bundled_paks_dir()]


# Lambda-wrapped factories so that monkeypatching the module-level
# ``DEFAULT_USER_PAKS_DIR`` / ``bundled_paks_dir`` / ``DEFAULT_ACTIVE_FILE``
# from tests is picked up at instantiation time (a literal default would
# bind at class-definition time and ignore the patch).
@dataclass
class PakRegistry:
    """Search a list of directories for PAKs and track the active pointer.

    Parameters are injectable so tests can run against ``tmp_path`` without
    touching ``~/.paty``.
    """

    paks_dirs: list[Path] = field(default_factory=lambda: _default_paks_dirs())
    active_file: Path = field(default_factory=lambda: DEFAULT_ACTIVE_FILE)

    def list(self) -> list[str]:
        """Names of all discoverable PAKs.

        Earlier entries in ``paks_dirs`` shadow later ones, so a
        user-installed PAK with the same name as a bundled one wins.
        """
        seen: dict[str, Path] = {}
        for d in self.paks_dirs:
            if not d.is_dir():
                continue
            for sub in sorted(d.iterdir()):
                if not sub.is_dir():
                    continue
                if (sub / "pak.yaml").is_file() and sub.name not in seen:
                    seen[sub.name] = sub
        return list(seen.keys())

    def get(self, name: str) -> Pak:
        """Load the PAK named ``name`` from the first directory that has it."""
        for d in self.paks_dirs:
            candidate = d / name
            if (candidate / "pak.yaml").is_file():
                return load_pak(candidate)
        msg = f"PAK not found: {name}"
        raise PakLoadError(msg)

    def active_name(self) -> str | None:
        """Return the contents of ``active.txt`` if set, else ``None``."""
        if not self.active_file.is_file():
            return None
        name = self.active_file.read_text().strip()
        return name or None

    def set_active(self, name: str) -> None:
        """Validate the PAK loads, then write its name to ``active.txt``."""
        self.get(name)
        self.active_file.parent.mkdir(parents=True, exist_ok=True)
        self.active_file.write_text(name)

    def active(self) -> Pak | None:
        """Load and return the currently active PAK, or ``None`` if unset."""
        name = self.active_name()
        if name is None:
            return None
        return self.get(name)
