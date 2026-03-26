"""Transcript-level test harness for call simulation.

Drives a conversation between the PATY LLM (via OpenAI API directly) and a
CallSimulator, using the same system prompt that run_bot constructs. No Pipecat
pipeline or audio services are involved — this tests the LLM's ability to
navigate IVR menus and converse with humans at the text level.
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from pipecat_outbound.prompt import build_system_prompt
from pipecat_outbound.simulator.engine import CallSimulator
from pipecat_outbound.simulator.scenario import Scenario


class TranscriptHarness:
    """Runs a simulated call at the transcript (text-only) level."""

    def __init__(
        self,
        scenario: Scenario,
        simulator: CallSimulator,
        *,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.scenario = scenario
        self.simulator = simulator
        self.model = model
        self.transcript: list[dict] = []

        self._system_prompt = build_system_prompt(
            target_who=scenario.bot_config.target_who,
            goal=scenario.bot_config.goal,
            impersonate=scenario.bot_config.impersonate,
            persona=scenario.bot_config.persona,
            secrets=scenario.bot_config.secrets,
        )

        self._client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._messages: list[dict] = [
            {"role": "system", "content": self._system_prompt},
        ]

    async def run(self, *, max_turns: int = 20, timeout: float = 60.0) -> list[dict]:
        """Execute the simulated call and return the transcript.

        Each turn is: simulator speaks → LLM responds.
        Continues until simulator reaches terminal state or max_turns exceeded.
        """
        # Get the initial greeting from the simulated party
        greeting = await self.simulator.get_greeting()
        self.transcript.append({"role": "user", "text": greeting, "turn": 0})
        self._messages.append({"role": "user", "content": greeting})

        turn = 0
        while turn < max_turns and not self.simulator.is_terminal:
            # Get PATY's response from the LLM
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._messages,
            )
            assistant_text = response.choices[0].message.content or ""

            self._messages.append({"role": "assistant", "content": assistant_text})
            self.transcript.append(
                {"role": "assistant", "text": assistant_text, "turn": turn}
            )

            turn += 1

            # Feed PATY's response to the simulator
            if self.simulator.is_terminal:
                break

            simulator_response = await self.simulator.receive(assistant_text)
            if not simulator_response or self.simulator.is_terminal:
                break

            self._messages.append({"role": "user", "content": simulator_response})
            self.transcript.append(
                {"role": "user", "text": simulator_response, "turn": turn}
            )

        return self.transcript
