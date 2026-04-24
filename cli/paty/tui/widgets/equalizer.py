"""Equalizer — stub bar display. Driven by audio frame levels in a later pass."""

from __future__ import annotations

from rich.align import Align
from rich.panel import Panel
from rich.text import Text

from paty.tui.theme import Theme

_BARS = "▁▂▃▄▅▆▇█"
_DEFAULT_CHANNELS = 16


def render_equalizer(theme: Theme, levels: list[float] | None = None) -> Panel:
    if not levels:
        levels = [0.0] * _DEFAULT_CHANNELS
    chars = []
    for lvl in levels:
        clamped = max(0.0, min(1.0, lvl))
        idx = int(clamped * (len(_BARS) - 1))
        chars.append(_BARS[idx])
    bars = Text("".join(chars), style=theme.equalizer)
    return Panel(
        Align.center(bars, vertical="middle"),
        title="equalizer",
        border_style=theme.border,
    )
