"""Conversation transcript — user/agent turns with streaming pending text."""

from __future__ import annotations

from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.padding import Padding
from rich.panel import Panel
from rich.segment import Segment
from rich.text import Text

from paty.tui.conversation import Conversation, Turn
from paty.tui.theme import Theme

_ROLE_LABEL = {"user": "you", "agent": "paty"}


def render_transcript(convo: Conversation, theme: Theme, *, status: str = "") -> Panel:
    if convo.turns:
        body: RenderableType = _TailScroll(
            [_render_turn(t, theme) for t in convo.turns]
        )
    else:
        body = Text("(waiting for events)", style="dim")
    return Panel(
        body,
        title="conversation",
        subtitle=status or None,
        border_style=theme.border,
    )


def _render_turn(turn: Turn, theme: Theme) -> Padding:
    role_style = theme.user if turn.role == "user" else theme.agent
    label = Text(f"{_ROLE_LABEL[turn.role]:>5} │ ", style=role_style)
    body = Text()
    if turn.committed:
        body.append(turn.committed)
    if turn.pending:
        if turn.committed:
            body.append(" ")
        body.append(turn.pending, style=theme.pending)
    if not body.plain:
        body.append("…", style="dim")
    return Padding(label + body, (0, 0, 0, 0))


class _TailScroll:
    """Render children into lines, keeping only the last `options.height`.

    Panel gives its body a fixed height when placed in a Layout; without this
    the transcript clips from the top (oldest shown) once it overflows. Here
    we render every turn at the panel's width, then slice to the tail so the
    view always sticks to the newest content.
    """

    def __init__(self, children: list[RenderableType]) -> None:
        self.children = children

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        # Render each child without a height cap — render_lines pads to
        # options.height otherwise, which would inflate each turn to the full
        # panel height and make tail-slicing meaningless.
        child_options = options.update(height=None)
        lines: list[list[Segment]] = []
        for child in self.children:
            lines.extend(console.render_lines(child, child_options, pad=False))
        height = options.height
        if height is not None:
            if height <= 0:
                return
            if len(lines) > height:
                lines = lines[-height:]
        for i, line in enumerate(lines):
            yield from line
            if i < len(lines) - 1:
                yield Segment.line()
