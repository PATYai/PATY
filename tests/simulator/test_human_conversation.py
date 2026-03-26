"""Transcript-level tests for human persona conversations.

These tests use the real OpenAI LLM to prove PATY can converse with a
human after IVR handoff. Requires OPENAI_API_KEY.
"""

import pytest

from tests.simulator.assertions import run_scenario_assertions

pytestmark = pytest.mark.llm


@pytest.mark.asyncio
async def test_insurance_agent_file_claim(transcript_harness):
    """PATY converses with a human insurance agent to file an auto claim."""
    harness = transcript_harness("insurance_agent_human.yaml")
    transcript = await harness.run(max_turns=12)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)
