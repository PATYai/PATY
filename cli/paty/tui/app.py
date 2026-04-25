"""`paty bus tui` — live conversation view subscribed to a running bus."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
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
from paty.tui.widgets.input import input_height, render_input
from paty.tui.widgets.transcript import render_transcript

# Show the "clearing" face while backspaces are arriving rapidly. Anything
# larger felt sticky after release; anything smaller flickered between
# "typing" and "clearing" during a hold-backspace.
_CLEARING_HOLD_S = 0.25
_CLEARING_REPEAT_S = 0.15
# How long after the last keystroke we consider the user actively typing.
# Long enough to bridge between words; short enough to drop back to idle
# when the user stops to think.
_TYPING_HOLD_S = 0.6


@dataclass
class UIState:
    convo: Conversation = field(default_factory=Conversation)
    agent_state: str = "idle"
    connection: str = ""
    theme: Theme = DAY
    muted: bool = False
    input_buffer: str = ""
    input_state: str | None = None  # None | "typing" | "clearing"


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


def _recompute_input_state(
    buffer: str, last_bs_ts: float, bs_streak: int, last_type_ts: float
) -> str | None:
    now = time.monotonic()
    if bs_streak >= 2 and (now - last_bs_ts) < _CLEARING_HOLD_S:
        return "clearing"
    if buffer and (now - last_type_ts) < _TYPING_HOLD_S:
        return "typing"
    return None


async def _run(url: str) -> None:
    console = Console()
    state = UIState(connection=f"connecting to {url}…")
    layout = build_layout()
    outbox: asyncio.Queue[str] = asyncio.Queue()
    last_bs_ts = 0.0
    bs_streak = 0
    last_type_ts = 0.0
    clearing_revert: asyncio.Handle | None = None
    typing_revert: asyncio.Handle | None = None

    def paint() -> None:
        _paint(layout, state, console.size.width)

    def submit(text: str) -> None:
        text = text.strip()
        if not text:
            return
        if text.startswith("/"):
            _run_slash_command(text, state, outbox)
            return
        outbox.put_nowait(json.dumps({"action": "chat.send", "text": text}))

    paint()

    with (
        _raw_tty() as fd,
        Live(layout, console=console, refresh_per_second=15, screen=True) as live,
    ):
        if fd is not None:
            loop = asyncio.get_running_loop()

            def revert_clearing() -> None:
                nonlocal bs_streak
                if state.input_state == "clearing":
                    bs_streak = 0
                    state.input_state = _recompute_input_state(
                        state.input_buffer, last_bs_ts, bs_streak, last_type_ts
                    )
                    paint()
                    live.refresh()

            def revert_typing() -> None:
                if state.input_state == "typing":
                    state.input_state = _recompute_input_state(
                        state.input_buffer, last_bs_ts, bs_streak, last_type_ts
                    )
                    paint()
                    live.refresh()

            def on_key() -> None:
                nonlocal last_bs_ts, bs_streak, last_type_ts
                nonlocal clearing_revert, typing_revert
                try:
                    raw = os.read(fd, 1024)
                except OSError:
                    return
                try:
                    chars = raw.decode("utf-8", errors="replace")
                except UnicodeDecodeError:
                    return
                dirty = False
                i = 0
                while i < len(chars):
                    ch = chars[i]
                    code = ord(ch)
                    if ch == "\x1b":
                        # Drop CSI escape sequences (arrow keys, etc.).
                        i += 1
                        if i < len(chars) and chars[i] == "[":
                            i += 1
                            while i < len(chars) and not chars[i].isalpha():
                                i += 1
                            i += 1
                        continue
                    if ch in ("\r", "\n"):
                        if state.input_buffer.strip():
                            submit(state.input_buffer)
                        state.input_buffer = ""
                        bs_streak = 0
                        dirty = True
                    elif code in (0x7F, 0x08):
                        if state.input_buffer:
                            state.input_buffer = state.input_buffer[:-1]
                        now = time.monotonic()
                        if (now - last_bs_ts) < _CLEARING_REPEAT_S:
                            bs_streak += 1
                        else:
                            bs_streak = 1
                        last_bs_ts = now
                        if clearing_revert is not None:
                            clearing_revert.cancel()
                        clearing_revert = loop.call_later(
                            _CLEARING_HOLD_S, revert_clearing
                        )
                        dirty = True
                    elif ch.isprintable():
                        state.input_buffer += ch
                        bs_streak = 0
                        last_type_ts = time.monotonic()
                        if typing_revert is not None:
                            typing_revert.cancel()
                        typing_revert = loop.call_later(_TYPING_HOLD_S, revert_typing)
                        dirty = True
                    i += 1
                if dirty:
                    state.input_state = _recompute_input_state(
                        state.input_buffer, last_bs_ts, bs_streak, last_type_ts
                    )
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


def _run_slash_command(text: str, state: UIState, outbox: asyncio.Queue[str]) -> None:
    cmd = text[1:].split(maxsplit=1)[0].lower()
    if cmd == "theme":
        state.theme = next_theme(state.theme)
        state.input_buffer = ""
    elif cmd == "mute":
        outbox.put_nowait(json.dumps({"action": "mute.toggle"}))
        state.input_buffer = ""
    # Unknown commands fall through silently — leaves them in the buffer
    # so the user sees what they typed and can correct it.


async def _drain_outbox(ws, outbox: asyncio.Queue[str]) -> None:
    try:
        while True:
            msg = await outbox.get()
            await ws.send(msg)
    except websockets.exceptions.ConnectionClosed:
        pass


def _paint(layout: Layout, state: UIState, console_width: int) -> None:
    status = f"{state.connection} · theme:{state.theme.name}"
    layout["transcript"].update(
        render_transcript(state.convo, state.theme, status=status),
    )
    layout["avatar"].update(
        render_avatar(
            state.agent_state,
            state.theme,
            muted=state.muted,
            input_state=state.input_state,
        )
    )
    layout["equalizer"].update(render_equalizer(state.theme))
    layout["input"].update(render_input(state.input_buffer, state.theme))
    layout["input"].size = input_height(state.input_buffer, console_width)


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
