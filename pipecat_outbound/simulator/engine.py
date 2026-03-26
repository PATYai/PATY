"""Call simulator engines for IVR state machines and human personas."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from pipecat_outbound.simulator.scenario import Scenario


class CallSimulator(ABC):
    """Base class for simulating the other end of a call."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self._history: list[dict] = []
        self._terminal = False

    async def get_greeting(self) -> str:
        """Return the initial greeting from the simulated party."""
        return self.scenario.initial_greeting

    @abstractmethod
    async def receive(self, text: str) -> str:
        """Receive what PATY said and return the simulated party's response."""
        ...

    @property
    def is_terminal(self) -> bool:
        return self._terminal

    @property
    def history(self) -> list[dict]:
        return list(self._history)


class IVRSimulator(CallSimulator):
    """Simulates an IVR phone menu system using a state machine."""

    def __init__(self, scenario: Scenario) -> None:
        super().__init__(scenario)
        assert scenario.type == "ivr"
        self._current_state = scenario.initial_state
        self._visited_states: list[str] = [scenario.initial_state]

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def visited_states(self) -> list[str]:
        return list(self._visited_states)

    async def receive(self, text: str) -> str:
        if self._terminal:
            return ""

        state = self.scenario.states[self._current_state]
        self._history.append(
            {"role": "paty", "text": text, "state": self._current_state}
        )

        # Try to match against transitions
        for transition in state.transitions:
            if re.search(transition.match, text, re.IGNORECASE):
                self._current_state = transition.next_state
                self._visited_states.append(self._current_state)
                next_state = self.scenario.states[self._current_state]

                if next_state.terminal:
                    self._terminal = True

                self._history.append(
                    {
                        "role": "ivr",
                        "text": next_state.prompt,
                        "state": self._current_state,
                    }
                )
                return next_state.prompt

        # No match — repeat current prompt
        self._history.append(
            {"role": "ivr", "text": state.prompt, "state": self._current_state}
        )
        return state.prompt

    def reached_state(self, state_name: str) -> bool:
        return state_name in self._visited_states


class PersonaSimulator(CallSimulator):
    """Simulates a human using scripted pattern-matched responses.

    Responses are consumed sequentially: the simulator tries to match the
    current (next expected) response first, then scans forward. Once a
    response is matched, earlier responses are not revisited. This prevents
    PATY's polite "thank you" phrasing from accidentally re-triggering an
    earlier pattern.
    """

    def __init__(self, scenario: Scenario) -> None:
        super().__init__(scenario)
        assert scenario.type == "human"
        self._default_response = "I'm sorry, could you repeat that?"
        # Build the ordered list of pattern responses (exclude default)
        self._pattern_responses = [r for r in scenario.responses if r.when is not None]
        self._next_index = 0
        # Extract the default response if one exists
        for r in scenario.responses:
            if r.when is None:
                self._default_response = r.say
                break

    async def receive(self, text: str) -> str:
        if self._terminal:
            return ""

        self._history.append({"role": "paty", "text": text})

        # Try matching from current position forward (never go backwards)
        for i in range(self._next_index, len(self._pattern_responses)):
            response = self._pattern_responses[i]
            if re.search(response.when, text, re.IGNORECASE):
                self._next_index = i + 1
                if response.terminal:
                    self._terminal = True
                self._history.append({"role": "human", "text": response.say})
                return response.say

        # Fallback to default
        self._history.append({"role": "human", "text": self._default_response})
        return self._default_response
