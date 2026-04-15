"""Static ASCII art logo widget."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from paty import __version__

_PHONE = [
    "┌───┐",
    "│ • │",
    "│ • │",
    "└───┘",
]

_PATY = [
    "██████   █████   ██████   ██  ██",
    "█    █   █   █     ██     ██████",
    "██████   █████     ██       ██  ",
    "█        █   █     ██       ██  ",
]


class LogoWidget(Static):
    """Renders the PATY ASCII logo with color styling."""

    DEFAULT_CSS = """
    LogoWidget {
        height: auto;
        max-height: 6;
        padding: 0 1;
    }
    """

    def on_mount(self) -> None:
        text = Text()
        for i in range(4):
            text.append(_PHONE[i], style="bold cyan")
            text.append("   ")
            text.append(_PATY[i], style="bold white")
            if i == 0:
                text.append(f"   v{__version__}", style="dim")
            text.append("\n")
        self.update(text)
