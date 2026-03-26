"""Fixtures for call simulator tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipecat_outbound.simulator.engine import IVRSimulator, PersonaSimulator
from pipecat_outbound.simulator.scenario import load_scenario
from tests.simulator.harness import TranscriptHarness

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def pytest_collection_modifyitems(items):
    """Auto-skip @pytest.mark.llm tests when OPENAI_API_KEY is not set."""
    if os.getenv("OPENAI_API_KEY"):
        return
    skip_llm = pytest.mark.skip(reason="OPENAI_API_KEY not set")
    for item in items:
        if "llm" in item.keywords:
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


@pytest.fixture
def transcript_harness(scenario_path):
    """Return a factory that creates a TranscriptHarness from a scenario filename."""

    def _create(name: str, *, model: str = "gpt-4o-mini") -> TranscriptHarness:
        path = scenario_path(name)
        scenario = load_scenario(path)
        if scenario.type == "ivr":
            simulator = IVRSimulator(scenario)
        else:
            simulator = PersonaSimulator(scenario)
        return TranscriptHarness(scenario, simulator, model=model)

    return _create
