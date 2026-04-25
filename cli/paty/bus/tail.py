"""`paty bus tail` — subscribe to a running bus and pretty-print events."""

from __future__ import annotations

import asyncio
import contextlib
import json

import websockets
from rich.console import Console

from paty.bus.codec import unpack_audio_frame

_STATE_COLOR = {
    "idle": "dim",
    "listening": "cyan",
    "thinking": "yellow",
    "speaking": "green",
}

_EVENT_COLOR = {
    "session.started": "bold green",
    "session.ended": "bold red",
    "user.speech_started": "cyan",
    "user.speech_stopped": "cyan",
    "user.transcript.partial": "dim cyan",
    "user.transcript.final": "bold cyan",
    "agent.thinking_started": "yellow",
    "agent.response.delta": "dim yellow",
    "agent.response.completed": "bold yellow",
    "agent.speech_started": "green",
    "agent.speech_stopped": "green",
    "state.changed": "magenta",
    "metrics.tick": "dim",
    "error": "bold red",
    "log": "dim",
    "input.muted": "bold magenta",
}


async def tail(url: str, *, show_audio: bool = True) -> None:
    console = Console()
    console.print(f"[dim]connecting to {url}...[/]")
    try:
        async with websockets.connect(url) as ws:
            console.print("[green]connected[/] — [dim]Ctrl+C to quit[/]\n")
            async for msg in ws:
                if isinstance(msg, bytes):
                    if show_audio:
                        _render_audio(console, msg)
                    continue
                _render_event(console, msg)
    except (OSError, websockets.exceptions.WebSocketException) as e:
        console.print(f"[red]connection error:[/] {e}")
        raise SystemExit(1) from e


def _render_event(console: Console, raw: str) -> None:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        console.print(f"[red]malformed event:[/] {raw!r}")
        return

    etype = event.get("type", "?")
    ts_ms = event.get("ts_ms", 0)
    seq = event.get("seq", 0)
    data = event.get("data", {}) or {}
    color = _EVENT_COLOR.get(etype, "white")

    prefix = f"[dim]{ts_ms:>7}ms #{seq:<4}[/] [{color}]{etype:<28}[/]"

    if etype == "state.changed":
        state = data.get("state", "?")
        state_color = _STATE_COLOR.get(state, "white")
        console.print(f"{prefix} [{state_color}]→ {state}[/]")
    elif etype in {"user.transcript.partial", "user.transcript.final"}:
        console.print(f'{prefix} "{data.get("text", "")}"')
    elif etype == "agent.response.delta":
        console.print(f"{prefix} {data.get('text', '')!r}")
    elif etype == "agent.response.completed":
        console.print(f'{prefix} "{data.get("text", "")}"')
    elif etype == "metrics.tick":
        parts = [f"{k}={v:.1f}" for k, v in data.items() if isinstance(v, int | float)]
        console.print(f"{prefix} {' '.join(parts)}")
    elif etype == "input.muted":
        muted = data.get("muted", False)
        console.print(f"{prefix} mic {'muted' if muted else 'unmuted'}")
    elif data:
        console.print(f"{prefix} {data}")
    else:
        console.print(prefix)


def _render_audio(console: Console, raw: bytes) -> None:
    try:
        frame = unpack_audio_frame(raw)
    except ValueError as e:
        console.print(f"[red]bad audio frame:[/] {e}")
        return
    stream_color = "cyan" if frame.stream.name == "MIC" else "green"
    console.print(
        f"[dim]{frame.ts_ms:>7}ms #{frame.seq:<4}[/] "
        f"[{stream_color}]audio[{frame.stream.name.lower():<5}][/] "
        f"[dim]sr={frame.sample_rate} {len(frame.pcm)}B[/]"
    )


def run(url: str, show_audio: bool) -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(tail(url, show_audio=show_audio))
