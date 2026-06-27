"""Fixtures for call simulator tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent.simulator.engine import IVRSimulator, PersonaSimulator
from agent.simulator.scenario import load_scenario
from tests.simulator.harness import TranscriptHarness, WaveformHarness

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

_WAVEFORM_KEYS = ("OPENAI_API_KEY",)


def pytest_collection_modifyitems(items):
    """Auto-skip tests when required API keys are missing."""
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    skip_llm = pytest.mark.skip(reason="OPENAI_API_KEY not set")
    skip_waveform = pytest.mark.skip(reason="OPENAI_API_KEY not set (waveform)")

    for item in items:
        if "waveform" in item.keywords and not has_openai:
            item.add_marker(skip_waveform)
        elif "llm" in item.keywords and not has_openai:
            item.add_marker(skip_llm)


@pytest.fixture
def scenario_path():
    """Return a function that resolves a scenario filename to its full path."""

    def _resolve(name: str) -> Path:
        path = SCENARIOS_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"Scenario not found: {path}")
        return path

    return _resolve


def _make_simulator(scenario):
    if scenario.type == "ivr":
        return IVRSimulator(scenario)
    return PersonaSimulator(scenario)


@pytest.fixture
def transcript_harness(scenario_path):
    """Return a factory that creates a TranscriptHarness from a scenario filename."""

    def _create(name: str, *, model: str = "gpt-4o-mini") -> TranscriptHarness:
        path = scenario_path(name)
        scenario = load_scenario(path)
        simulator = _make_simulator(scenario)
        return TranscriptHarness(scenario, simulator, model=model)

    return _create


@pytest.fixture
def waveform_harness(scenario_path):
    """Return a factory that creates a WaveformHarness from a scenario filename."""

    def _create(
        name: str, *, model: str = "gpt-4o-mini", tts_voice: str = "alloy"
    ) -> WaveformHarness:
        path = scenario_path(name)
        scenario = load_scenario(path)
        simulator = _make_simulator(scenario)
        return WaveformHarness(scenario, simulator, model=model, tts_voice=tts_voice)

    return _create
