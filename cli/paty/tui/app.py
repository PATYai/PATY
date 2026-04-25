"""`paty bus tui` — live conversation view subscribed to a running bus."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

import websockets
from rich.console import Console
from rich.layout import Layout
from rich.live import Live

from paty.tui.conversation import Conversation
from paty.tui.layout import build_layout
from paty.tui.theme import DAY, Theme, next_theme
from paty.tui.widgets.avatar import render_avatar
from paty.tui.widgets.equalizer import render_equalizer
from paty.tui.widgets.transcript import render_transcript


@dataclass
class UIState:
    convo: Conversation = field(default_factory=Conversation)
    agent_state: str = "idle"
    connection: str = ""
    theme: Theme = DAY
    muted: bool = False


@contextlib.contextmanager
def _raw_tty() -> Iterator[int | None]:
    """Put stdin in cbreak so single keys arrive without waiting for Enter.

    Yields the stdin fd, or None if stdin isn't a TTY (piped input) — in that
    case key handling is silently skipped.
    """
    if not sys.stdin.isatty():
        yield None
        return
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield fd
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def _run(url: str) -> None:
    console = Console()
    state = UIState(connection=f"connecting to {url}…")
    layout = build_layout()
    outbox: asyncio.Queue[str] = asyncio.Queue()

    def paint() -> None:
        _paint(layout, state)

    paint()

    with (
        _raw_tty() as fd,
        Live(layout, console=console, refresh_per_second=15, screen=True) as live,
    ):
        if fd is not None:
            loop = asyncio.get_running_loop()

            def on_key() -> None:
                try:
                    data = os.read(fd, 64)
                except OSError:
                    return
                dirty = False
                for b in data:
                    ch = chr(b)
                    if ch == "t":
                        state.theme = next_theme(state.theme)
                        dirty = True
                    elif ch == "m":
                        outbox.put_nowait(json.dumps({"action": "mute.toggle"}))
                if dirty:
                    paint()
                    live.refresh()

            loop.add_reader(fd, on_key)

        try:
            async with websockets.connect(url) as ws:
                state.connection = f"connected · {url}"
                paint()
                sender = asyncio.create_task(_drain_outbox(ws, outbox))
                try:
                    async for msg in ws:
                        if isinstance(msg, bytes):
                            continue
                        if _dispatch(state, msg):
                            paint()
                finally:
                    sender.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await sender
        except (OSError, websockets.exceptions.WebSocketException) as e:
            state.connection = f"disconnected: {e}"
            paint()
            live.refresh()
            raise SystemExit(1) from e


async def _drain_outbox(ws, outbox: asyncio.Queue[str]) -> None:
    try:
        while True:
            msg = await outbox.get()
            await ws.send(msg)
    except websockets.exceptions.ConnectionClosed:
        pass


def _paint(layout: Layout, state: UIState) -> None:
    status = f"{state.connection} · theme:{state.theme.name} · t:toggle · m:mute"
    layout["transcript"].update(
        render_transcript(state.convo, state.theme, status=status),
    )
    layout["avatar"].update(
        render_avatar(state.agent_state, state.theme, muted=state.muted)
    )
    layout["equalizer"].update(render_equalizer(state.theme))


def _dispatch(state: UIState, raw: str) -> bool:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return False
    etype = event.get("type")
    data = event.get("data") or {}
    text = data.get("text", "")
    if etype == "user.transcript.partial":
        state.convo.user_partial(text)
    elif etype == "user.transcript.final":
        state.convo.user_final(text)
    elif etype == "agent.response.delta":
        state.convo.agent_delta(text)
    elif etype == "agent.response.completed":
        state.convo.agent_final(text)
    elif etype == "state.changed":
        state.agent_state = data.get("state", state.agent_state)
    elif etype == "input.muted":
        state.muted = bool(data.get("muted", False))
    else:
        return False
    return True


def run(url: str) -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(url))
