"""Transcript-level tests for IVR phone menu navigation.

These tests use the real OpenAI LLM to prove PATY can navigate IVR menus
and reach a live agent. Requires OPENAI_API_KEY.
"""

import pytest

from tests.simulator.assertions import run_scenario_assertions

pytestmark = pytest.mark.llm


@pytest.mark.asyncio
async def test_insurance_claims_navigate_to_agent(transcript_harness):
    """PATY navigates an insurance IVR to reach the claims department."""
    harness = transcript_harness("insurance_claims_ivr.yaml")
    transcript = await harness.run(max_turns=10)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)


@pytest.mark.asyncio
async def test_bank_navigate_with_pin(transcript_harness):
    """PATY navigates a bank IVR, provides PIN, and reaches an agent."""
    harness = transcript_harness("bank_account_ivr.yaml")
    transcript = await harness.run(max_turns=12)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)


@pytest.mark.asyncio
async def test_doctor_appointment_scheduling(transcript_harness):
    """PATY navigates a medical office IVR to reach the scheduling desk."""
    harness = transcript_harness("doctor_appointment_ivr.yaml")
    transcript = await harness.run(max_turns=8)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)
