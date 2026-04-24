"""Conversation state assembled from bus transcript events.

Turn boundaries are driven by role-switch, not by transcript finals. STT
often emits multiple finals within a single utterance (pauses, filler
words); those all belong to the same user turn. A new turn opens only
when the other role starts speaking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "agent"]


@dataclass
class Turn:
    role: Role
    committed: str = ""
    pending: str = ""

    @property
    def text(self) -> str:
        parts = [p for p in (self.committed, self.pending) if p]
        return " ".join(parts)


class Conversation:
    """Accumulates user/agent turns from bus transcript events."""

    def __init__(self) -> None:
        self.turns: list[Turn] = []

    def _turn_for(self, role: Role) -> Turn:
        if self.turns and self.turns[-1].role == role:
            return self.turns[-1]
        turn = Turn(role=role)
        self.turns.append(turn)
        return turn

    def user_partial(self, text: str) -> None:
        self._turn_for("user").pending = text

    def user_final(self, text: str) -> None:
        turn = self._turn_for("user")
        turn.committed = f"{turn.committed} {text}".strip() if turn.committed else text
        turn.pending = ""

    def agent_delta(self, text: str) -> None:
        self._turn_for("agent").committed += text

    def agent_final(self, text: str) -> None:
        turn = self._turn_for("agent")
        if text:
            turn.committed = text
        turn.pending = ""
