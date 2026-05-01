"""DOS-boot-style startup screen: logo on top, mascot left, logs right.

Owns the Rich :class:`~rich.live.Live` for the boot phase. Knows nothing
about subprocesses — :func:`write_line` is the only ingress, callable from
any thread.
"""

from __future__ import annotations

import threading
from collections import deque

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

# README banner. Box on the left is the mascot face, the rest spells PATY.
_LOGO = (
    "┌───┐   ██████   █████   ██████   ██  ██\n"
    "│ • │   █    █   █   █     ██     ██████\n"
    "│ • │   ██████   █████     ██       ██  \n"
    "└───┘   █        █   █     ██       ██  "
)

# Larger boxy face for the dedicated mascot panel.
_MASCOT = (
    "┌───────────┐\n"
    "│           │\n"
    "│     •     │\n"
    "│           │\n"
    "│     •     │\n"
    "│           │\n"
    "│   ─────   │\n"
    "│           │\n"
    "└───────────┘"
)


class BootScreen:
    """Three-region boot UI driven by a tail-of-log buffer.

    Lifecycle: ``start()`` → many ``write_line()`` calls → ``stop()``.
    ``write_line`` is thread-safe.
    """

    def __init__(self, *, max_lines: int = 500) -> None:
        self._lines: deque[Text] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._console = Console()
        self._layout = self._build_layout()
        self._live: Live | None = None

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=6),
            Layout(name="body"),
        )
        layout["body"].split_row(
            Layout(name="mascot", size=17),
            Layout(name="logs"),
        )
        layout["header"].update(self._render_header())
        layout["mascot"].update(self._render_mascot())
        layout["logs"].update(self._render_logs())
        return layout

    def _render_header(self) -> Panel:
        return Panel(
            Align.center(Text(_LOGO, style="bold cyan")),
            border_style="cyan",
        )

    def _render_mascot(self) -> Panel:
        return Panel(
            Align.center(Text(_MASCOT, style="bold magenta"), vertical="middle"),
            title="paty",
            border_style="magenta",
        )

    def _render_logs(self) -> Panel:
        with self._lock:
            body = (
                Group(*self._lines)
                if self._lines
                else Text("booting…", style="dim")
            )
        return Panel(body, title="boot log", border_style="cyan")

    def start(self) -> None:
        if self._live is not None:
            return
        self._live = Live(
            self._layout,
            console=self._console,
            refresh_per_second=10,
            screen=True,
        )
        self._live.start()

    def write_line(self, line: str) -> None:
        line = line.rstrip("\n")
        if not line:
            return
        rendered = Text.from_ansi(line, no_wrap=False)
        with self._lock:
            self._lines.append(rendered)
        self._layout["logs"].update(self._render_logs())

    def stop(self) -> None:
        if self._live is None:
            return
        self._live.stop()
        self._live = None
