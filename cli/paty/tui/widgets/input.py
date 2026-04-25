"""Input bar — collects typed messages for the chat.send bus action."""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from paty.tui.theme import Theme

PREFIX = "🁫 "
_MIN_LINES = 1
_MAX_LINES = 8
_PANEL_OVERHEAD = 2  # top + bottom border
_INNER_PAD = 4  # 2 border chars + 1 left/right padding


def render_input(buffer: str, theme: Theme) -> Panel:
    body = Text()
    body.append(PREFIX, style="bold")
    if buffer:
        body.append(buffer)
    else:
        body.append("type to chat · /theme · /mute · enter:send", style="dim")
    return Panel(body, border_style=theme.border, padding=(0, 1))


def input_height(buffer: str, console_width: int) -> int:
    """Total panel height (incl. borders) for the input at the given width."""
    inner = max(1, console_width - _INNER_PAD)
    visible = PREFIX + (buffer or "")
    rendered_lines = 0
    for line in visible.split("\n"):
        rendered_lines += max(1, (len(line) + inner - 1) // inner)
    rendered_lines = min(_MAX_LINES, max(_MIN_LINES, rendered_lines))
    return rendered_lines + _PANEL_OVERHEAD
