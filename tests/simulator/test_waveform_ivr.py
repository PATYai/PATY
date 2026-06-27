"""Waveform-level tests for IVR navigation through audio round-trips.

These tests pass every exchange through TTS→STT to verify the full audio
pipeline preserves meaning. They prove that PATY can still navigate IVR
menus when audio encoding, TTS voice quality, and STT recognition are in
the loop.

Requires OPENAI_API_KEY. Runs on merge to main only.
"""

import pytest

from tests.simulator.assertions import run_scenario_assertions

pytestmark = pytest.mark.waveform


@pytest.mark.asyncio
async def test_insurance_claims_waveform(waveform_harness):
    """PATY navigates insurance IVR through audio round-trips."""
    harness = waveform_harness("insurance_claims_ivr.yaml")
    transcript = await harness.run(max_turns=10)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)


@pytest.mark.asyncio
async def test_bank_navigate_waveform(waveform_harness):
    """PATY navigates bank IVR with PIN through audio round-trips."""
    harness = waveform_harness("bank_account_ivr.yaml")
    transcript = await harness.run(max_turns=12)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)


@pytest.mark.asyncio
async def test_doctor_appointment_waveform(waveform_harness):
    """PATY navigates medical office IVR through audio round-trips."""
    harness = waveform_harness("doctor_appointment_ivr.yaml")
    transcript = await harness.run(max_turns=8)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)


@pytest.mark.asyncio
async def test_human_agent_waveform(waveform_harness):
    """PATY converses with human agent through audio round-trips."""
    harness = waveform_harness("insurance_agent_human.yaml")
    transcript = await harness.run(max_turns=12)
    run_scenario_assertions(harness.scenario, harness.simulator, transcript)
