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

# Header banner — just the PATY wordmark; mascot lives in the left pane.
_LOGO = (
    "██████   █████   ██████   ██  ██\n"
    "█    █   █   █     ██     ██████\n"
    "██████   █████     ██       ██  \n"
    "█        █   █     ██       ██  "
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
            border_style="magenta",
        )

    def _render_logs(self) -> Panel:
        with self._lock:
            if not self._lines:
                body: Group | Text = Text("booting…", style="dim")
            else:
                body = Group(*self._tail_for_viewport())
        return Panel(body, title="boot log", border_style="cyan")

    def _tail_for_viewport(self) -> list[Text]:
        """Return the most recent lines that fit the logs panel's visible area.

        Rich clips overflowing Group content at the bottom, so a naive render
        keeps the oldest lines on screen instead of the newest. We measure
        the available rows (panel border + padding subtracted) and walk the
        deque from the back, counting wrapped rows, until the budget runs out.
        """
        size = self._console.size
        # body height = total - header(6); logs panel eats 2 rows of border
        # and the default Panel padding adds another 2 rows (top + bottom).
        visible_rows = max(1, size.height - 6 - 2 - 2)
        # logs panel width = total - mascot column(17) - logs borders(2) - padding(2).
        inner_width = max(1, size.width - 17 - 2 - 2)

        selected: list[Text] = []
        used = 0
        for line in reversed(self._lines):
            rows = max(1, -(-line.cell_len // inner_width))  # ceil division
            if used + rows > visible_rows and selected:
                break
            selected.append(line)
            used += rows
            if used >= visible_rows:
                break
        selected.reverse()
        return selected

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
