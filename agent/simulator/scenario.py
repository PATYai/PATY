"""YAML scenario loader and validation for call simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Transition:
    """A single state transition triggered by regex match."""

    match: str
    next_state: str


@dataclass
class SimulatorState:
    """A state in an IVR state machine."""

    name: str
    prompt: str
    transitions: list[Transition] = field(default_factory=list)
    terminal: bool = False
    transfer: bool = False


@dataclass
class PersonaResponse:
    """A scripted response for a persona simulator."""

    say: str
    when: str | None = None  # None means default/fallback
    terminal: bool = False


@dataclass
class BotConfig:
    """Configuration for the PATY bot during a scenario."""

    target_who: str
    goal: str
    impersonate: bool = False
    persona: str | None = None
    secrets: dict[str, str] = field(default_factory=dict)


@dataclass
class Assertion:
    """A single assertion to validate after a scenario run."""

    type: str
    state: str | None = None
    role: str | None = None
    pattern: str | None = None
    value: int | None = None


@dataclass
class Scenario:
    """A complete call simulation scenario."""

    name: str
    type: str  # "ivr" or "human"
    initial_greeting: str
    bot_config: BotConfig
    assertions: list[Assertion] = field(default_factory=list)

    # IVR-specific
    initial_state: str | None = None
    states: dict[str, SimulatorState] = field(default_factory=dict)

    # Human-specific
    responses: list[PersonaResponse] = field(default_factory=list)


def _parse_bot_config(raw: dict) -> BotConfig:
    return BotConfig(
        target_who=raw["target_who"],
        goal=raw["goal"],
        impersonate=raw.get("impersonate", False),
        persona=raw.get("persona"),
        secrets=raw.get("secrets", {}),
    )


def _parse_assertions(raw_list: list[dict]) -> list[Assertion]:
    return [
        Assertion(
            type=a["type"],
            state=a.get("state"),
            role=a.get("role"),
            pattern=a.get("pattern"),
            value=a.get("value"),
        )
        for a in raw_list
    ]


def _parse_ivr_states(raw_states: dict) -> dict[str, SimulatorState]:
    states = {}
    for name, state_data in raw_states.items():
        transitions = [
            Transition(match=t["match"], next_state=t["next"])
            for t in state_data.get("transitions", [])
        ]
        states[name] = SimulatorState(
            name=name,
            prompt=state_data["prompt"],
            transitions=transitions,
            terminal=state_data.get("terminal", False),
            transfer=state_data.get("transfer", False),
        )
    return states


def _parse_responses(raw_responses: list[dict]) -> list[PersonaResponse]:
    responses = []
    for r in raw_responses:
        if "default" in r:
            responses.append(PersonaResponse(say=r["default"]))
        else:
            responses.append(
                PersonaResponse(
                    when=r.get("when"),
                    say=r["say"],
                    terminal=r.get("terminal", False),
                )
            )
    return responses


def _validate_ivr(scenario: Scenario) -> None:
    if not scenario.initial_state:
        raise ValueError(f"IVR scenario '{scenario.name}' missing initial_state")
    if scenario.initial_state not in scenario.states:
        raise ValueError(
            f"initial_state '{scenario.initial_state}' not found in states"
        )
    terminal_count = sum(1 for s in scenario.states.values() if s.terminal)
    if terminal_count == 0:
        raise ValueError(f"IVR scenario '{scenario.name}' has no terminal states")
    for state in scenario.states.values():
        for t in state.transitions:
            if t.next_state not in scenario.states:
                raise ValueError(
                    f"State '{state.name}' transition target '{t.next_state}' not found"
                )


def _validate_human(scenario: Scenario) -> None:
    if not scenario.responses:
        raise ValueError(f"Human scenario '{scenario.name}' has no responses")


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a scenario from a YAML file."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    scenario_type = raw["type"]
    bot_config = _parse_bot_config(raw["bot_config"])
    assertions = _parse_assertions(raw.get("assertions", []))

    scenario = Scenario(
        name=raw["name"],
        type=scenario_type,
        initial_greeting=raw["initial_greeting"],
        bot_config=bot_config,
        assertions=assertions,
    )

    if scenario_type == "ivr":
        scenario.initial_state = raw.get("initial_state")
        scenario.states = _parse_ivr_states(raw.get("states", {}))
        _validate_ivr(scenario)
    elif scenario_type == "human":
        scenario.responses = _parse_responses(raw.get("responses", []))
        _validate_human(scenario)
    else:
        raise ValueError(f"Unknown scenario type: {scenario_type}")

    return scenario
