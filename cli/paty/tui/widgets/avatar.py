"""Avatar — stub face that reflects the current agent state."""

from __future__ import annotations

from rich.align import Align
from rich.panel import Panel
from rich.text import Text

from paty.tui.theme import Theme

_FACES = {
    "idle": "(• ◡ •)",
    "listening": "(• ᴥ •)",
    "thinking": "(- _ -)",
    "speaking": "(• o •)",
}


def _state_style(state: str, theme: Theme) -> str:
    return {
        "idle": theme.state_idle,
        "listening": theme.state_listening,
        "thinking": theme.state_thinking,
        "speaking": theme.state_speaking,
    }.get(state, theme.state_idle)


def render_avatar(state: str, theme: Theme) -> Panel:
    face = _FACES.get(state, _FACES["idle"])
    style = _state_style(state, theme)
    body = Text()
    body.append(f"{face}\n\n", style=style)
    body.append(state, style=f"bold {style}")
    return Panel(
        Align.center(body, vertical="middle"),
        title="avatar",
        border_style=theme.border,
    )
