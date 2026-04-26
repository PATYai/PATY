"""Avatar — stub face that reflects the current agent state."""

from __future__ import annotations

from rich.align import Align
from rich.panel import Panel
from rich.text import Text

from paty.tui.theme import Theme

# Built-in fallback faces.  Used when no PAK avatar is in scope, or when
# the PAK avatar is missing a particular state.
_FACES = {
    "idle": "(• ◡ •)",
    "listening": "(• ᴥ •)",
    "thinking": "(- _ -)",
    "speaking": "(• o •)",
}

# Input-driven overrides — change the face without changing the state label.
# These are TUI-internal (typing/clearing aren't agent states), so they are
# never overridden by a PAK.
_INPUT_FACES = {
    "typing": "(✻ ◡ ✻)",
    "clearing": "(✖ _ ✖)",
}


def _resolve_face(state: str, override: dict[str, str] | None) -> str:
    if override is not None and state in override:
        return override[state]
    return _FACES.get(state, _FACES["idle"])


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
    state_faces: dict[str, str] | None = None,
) -> Panel:
    """Render the avatar panel.

    ``state_faces`` is the inline avatar shipped by the active PAK over
    ``session.started``.  When set, it wins for any state it defines;
    states it doesn't define fall back to the built-in ``_FACES``.
    Input-driven overrides (typing/clearing) always take precedence — they
    track local keyboard state, not agent state.
    """
    face = _INPUT_FACES.get(input_state or "", _resolve_face(state, state_faces))
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
