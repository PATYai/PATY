"""Test harnesses for call simulation.

Two harnesses:

- TranscriptHarness: text-only, tests LLM navigation ability (every MR)
- WaveformHarness: adds TTS→STT round-trips to test audio fidelity (merge to main)

Both drive a conversation between the PATY LLM (via OpenAI API) and a
CallSimulator using the same system prompt that run_bot constructs.
"""

from __future__ import annotations

import io
import os

from openai import AsyncOpenAI

from agent.prompt import build_system_prompt
from agent.simulator.engine import CallSimulator
from agent.simulator.scenario import Scenario


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


class WaveformHarness:
    """Runs a simulated call with TTS→STT audio round-trips.

    Same conversation loop as TranscriptHarness, but every text exchange
    passes through TTS (text→audio) then STT (audio→text) to test that
    the audio pipeline preserves meaning. This catches:
    - STT misrecognitions of IVR prompts
    - TTS producing unintelligible audio
    - Audio encoding/quality issues at telephony sample rates

    Uses OpenAI TTS (tts-1) and Whisper (whisper-1) for the audio
    round-trip since they have simple batch APIs.
    """

    def __init__(
        self,
        scenario: Scenario,
        simulator: CallSimulator,
        *,
        model: str = "gpt-4o-mini",
        tts_voice: str = "alloy",
    ) -> None:
        self.scenario = scenario
        self.simulator = simulator
        self.model = model
        self.tts_voice = tts_voice
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

    async def _text_to_speech(self, text: str) -> bytes:
        """Convert text to audio bytes via OpenAI TTS."""
        response = await self._client.audio.speech.create(
            model="tts-1",
            voice=self.tts_voice,
            input=text,
            response_format="mp3",
        )
        return response.content

    async def _speech_to_text(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes via OpenAI Whisper."""
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.mp3"
        transcript = await self._client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        return transcript.text

    async def _audio_round_trip(self, text: str) -> str:
        """Pass text through TTS→STT and return what was heard."""
        audio = await self._text_to_speech(text)
        return await self._speech_to_text(audio)

    async def run(self, *, max_turns: int = 20) -> list[dict]:
        """Execute the simulated call with audio round-trips.

        Flow per turn:
        1. Simulator produces text → TTS → audio → STT → heard_text
        2. heard_text sent to LLM as what PATY hears
        3. LLM produces response text
        4. Response text → TTS → audio → STT → heard_by_simulator
        5. heard_by_simulator fed to simulator.receive()
        """
        # Initial greeting: simulator text → audio → what PATY hears
        greeting_text = await self.simulator.get_greeting()
        heard_greeting = await self._audio_round_trip(greeting_text)

        self.transcript.append(
            {
                "role": "user",
                "text": greeting_text,
                "heard": heard_greeting,
                "turn": 0,
            }
        )
        self._messages.append({"role": "user", "content": heard_greeting})

        turn = 0
        while turn < max_turns and not self.simulator.is_terminal:
            # LLM responds based on what it heard
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._messages,
            )
            assistant_text = response.choices[0].message.content or ""
            self._messages.append({"role": "assistant", "content": assistant_text})

            # PATY's response → audio → what the other party hears
            heard_by_other = await self._audio_round_trip(assistant_text)

            self.transcript.append(
                {
                    "role": "assistant",
                    "text": assistant_text,
                    "heard": heard_by_other,
                    "turn": turn,
                }
            )

            turn += 1

            if self.simulator.is_terminal:
                break

            # Simulator receives what it heard (post-STT), not the raw LLM text
            simulator_response = await self.simulator.receive(heard_by_other)
            if not simulator_response or self.simulator.is_terminal:
                break

            # Simulator's response → audio → what PATY hears
            heard_by_paty = await self._audio_round_trip(simulator_response)

            self.transcript.append(
                {
                    "role": "user",
                    "text": simulator_response,
                    "heard": heard_by_paty,
                    "turn": turn,
                }
            )
            self._messages.append({"role": "user", "content": heard_by_paty})

        return self.transcript
