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

# Input-driven overrides — change the face without changing the state label.
_INPUT_FACES = {
    "typing": "(✻ ◡ ✻)",
    "clearing": "(✖ _ ✖)",
}


def _state_style(state: str, theme: Theme) -> str:
    return {
        "idle": theme.state_idle,
        "listening": theme.state_listening,
        "thinking": theme.state_thinking,
        "speaking": theme.state_speaking,
    }.get(state, theme.state_idle)


def render_avatar(
    state: str,
    theme: Theme,
    *,
    muted: bool = False,
    input_state: str | None = None,
) -> Panel:
    face = _INPUT_FACES.get(input_state or "", _FACES.get(state, _FACES["idle"]))
    style = _state_style(state, theme)
    body = Text()
    body.append(f"{face}\n\n", style=style)
    body.append(state, style=f"bold {style}")
    subtitle = Text()
    if muted:
        subtitle.append("● mic muted", style=f"bold {theme.state_thinking}")
    else:
        subtitle.append("○ mic live", style=theme.state_idle)
    return Panel(
        Align.center(body, vertical="middle"),
        title="avatar",
        subtitle=subtitle,
        subtitle_align="right",
        border_style=theme.border,
    )
