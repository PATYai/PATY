"""Assertion helpers for call simulation test scenarios."""

from __future__ import annotations

import re

from agent.simulator.engine import CallSimulator, IVRSimulator
from agent.simulator.scenario import Scenario


def assert_reached_state(simulator: IVRSimulator, state: str) -> None:
    """Assert the IVR simulator visited a specific state."""
    assert state in simulator.visited_states, (
        f"Expected state '{state}' was never reached. "
        f"Visited: {simulator.visited_states}"
    )


def assert_reached_terminal(simulator: CallSimulator) -> None:
    """Assert the simulator reached a terminal state."""
    assert simulator.is_terminal, (
        "Expected simulator to reach a terminal state, but it did not. "
        f"History: {[e.get('text', '')[:60] for e in simulator.history[-4:]]}"
    )


def assert_transcript_contains(transcript: list[dict], role: str, pattern: str) -> None:
    """Assert at least one transcript entry for role matches the regex pattern."""
    entries = [e for e in transcript if e.get("role") == role]
    assert any(re.search(pattern, e["text"], re.IGNORECASE) for e in entries), (
        f"No {role} transcript matched /{pattern}/. "
        f"Entries: {[e['text'][:80] for e in entries]}"
    )


def assert_max_turns(transcript: list[dict], max_turns: int) -> None:
    """Assert the conversation did not exceed max_turns assistant responses."""
    turns = len([e for e in transcript if e.get("role") == "assistant"])
    assert turns <= max_turns, f"Took {turns} turns, max was {max_turns}"


def run_scenario_assertions(
    scenario: Scenario,
    simulator: CallSimulator,
    transcript: list[dict],
) -> None:
    """Run all assertions defined in the scenario YAML."""
    for assertion in scenario.assertions:
        atype = assertion.type

        if atype == "reached_state":
            assert isinstance(simulator, IVRSimulator)
            assert assertion.state is not None
            assert_reached_state(simulator, assertion.state)

        elif atype == "reached_terminal":
            assert_reached_terminal(simulator)

        elif atype == "transcript_contains":
            assert assertion.role is not None
            assert assertion.pattern is not None
            assert_transcript_contains(transcript, assertion.role, assertion.pattern)

        elif atype == "max_turns":
            assert assertion.value is not None
            assert_max_turns(transcript, assertion.value)

        else:
            raise ValueError(f"Unknown assertion type: {atype}")
