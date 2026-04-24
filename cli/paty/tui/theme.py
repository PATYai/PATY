"""Color themes for the TUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    user: str
    agent: str
    border: str
    pending: str
    equalizer: str
    state_idle: str
    state_listening: str
    state_thinking: str
    state_speaking: str


DAY = Theme(
    name="day",
    user="bold blue",
    agent="bold black",
    border="grey30",
    pending="grey50 italic",
    equalizer="steel_blue",
    state_idle="grey27",
    state_listening="steel_blue1",
    state_thinking="dark_khaki",
    state_speaking="spring_green3",
)


NIGHT = Theme(
    name="night",
    user="bold cyan",
    agent="bold magenta",
    border="dim",
    pending="dim italic",
    equalizer="cyan",
    state_idle="dim",
    state_listening="cyan",
    state_thinking="yellow",
    state_speaking="green",
)


def next_theme(current: Theme) -> Theme:
    return NIGHT if current is DAY else DAY
