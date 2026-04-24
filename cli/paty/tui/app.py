"""`paty bus tui` — live conversation view subscribed to a running bus."""

from __future__ import annotations

import asyncio
import contextlib
import json

import websockets
from rich.console import Console, Group
from rich.live import Live
from rich.padding import Padding
from rich.text import Text

from paty.tui.conversation import Conversation, Turn

_ROLE_LABEL = {"user": "you", "agent": "paty"}
_ROLE_STYLE = {"user": "bold cyan", "agent": "bold magenta"}


def _render(convo: Conversation, status: str) -> Group:
    items: list = []
    for turn in convo.turns:
        items.append(_render_turn(turn))
    items.append(Text(status, style="dim"))
    return Group(*items)


def _render_turn(turn: Turn) -> Padding:
    label = Text(f"{_ROLE_LABEL[turn.role]:>5} │ ", style=_ROLE_STYLE[turn.role])
    body = Text()
    if turn.committed:
        body.append(turn.committed)
    if turn.pending:
        if turn.committed:
            body.append(" ")
        body.append(turn.pending, style="dim italic")
    if not body.plain:
        body.append("…", style="dim")
    return Padding(label + body, (0, 0, 0, 0))


async def _run(url: str) -> None:
    console = Console()
    convo = Conversation()
    status = f"connecting to {url}…"

    with Live(_render(convo, status), console=console, refresh_per_second=15) as live:
        try:
            async with websockets.connect(url) as ws:
                status = f"connected · {url}"
                live.update(_render(convo, status))
                async for msg in ws:
                    if isinstance(msg, bytes):
                        continue
                    if _dispatch(convo, msg):
                        live.update(_render(convo, status))
        except (OSError, websockets.exceptions.WebSocketException) as e:
            live.update(_render(convo, f"[red]disconnected: {e}[/]"))
            raise SystemExit(1) from e


def _dispatch(convo: Conversation, raw: str) -> bool:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return False
    etype = event.get("type")
    data = event.get("data") or {}
    text = data.get("text", "")
    if etype == "user.transcript.partial":
        convo.user_partial(text)
    elif etype == "user.transcript.final":
        convo.user_final(text)
    elif etype == "agent.response.delta":
        convo.agent_delta(text)
    elif etype == "agent.response.completed":
        convo.agent_final(text)
    else:
        return False
    return True


def run(url: str) -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(url))
