"""Startup orchestrator: boot screen + `paty run` + handoff to `paty bus tui`.

Public surface is intentionally tiny — :func:`launch` is the only entry
point. Internals split into :mod:`paty.startup.boot_screen` (Rich UI) and
:mod:`paty.startup.launcher` (subprocess lifecycle) so either can be
swapped without touching the other.
"""

from paty.startup.launcher import launch

__all__ = ["launch"]
