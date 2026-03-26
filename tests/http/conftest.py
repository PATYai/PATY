"""
Fixtures for HTTP integration tests against the PATY bot FastAPI service.

All pipecat / opentelemetry modules are pre-mocked at sys.modules level so that
importing agent.server (and transitively bot.py) doesn't require the
real Pipecat stack to be installed.

The root tests/conftest.py already patches:
  pipecat, pipecat.transports, pipecat.transports.base_transport,
  pipecat.transports.services, pipecat.transports.services.daily,
  pipecat.audio, pipecat.audio.vad, pipecat.audio.vad.silero

We add the remaining modules needed by bot.py / server.py here.
"""

import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Additional sys.modules mocks (complement the root conftest)
# ---------------------------------------------------------------------------
_additional_mocks = [
    "pipecat.frames",
    "pipecat.frames.frames",
    "pipecat.pipeline",
    "pipecat.pipeline.pipeline",
    "pipecat.pipeline.runner",
    "pipecat.pipeline.task",
    "pipecat.processors",
    "pipecat.processors.aggregators",
    "pipecat.processors.aggregators.llm_context",
    "pipecat.processors.aggregators.llm_response_universal",
    "pipecat.services",
    "pipecat.services.assemblyai",
    "pipecat.services.assemblyai.models",
    "pipecat.services.assemblyai.stt",
    "pipecat.services.cartesia",
    "pipecat.services.cartesia.tts",
    "pipecat.services.openai",
    "pipecat.services.openai.llm",
    "pipecat.transports.daily",
    "pipecat.transports.daily.transport",
    "pipecat.observers",
    "pipecat.observers.base_observer",
    "pipecat.observers.loggers",
    "pipecat.observers.loggers.metrics_log_observer",
    "pipecat.observers.turn_tracking_observer",
    "pipecat.turns",
    "pipecat.turns.user_turn_strategies",
    "pipecat.audio.vad.vad_analyzer",
    "pipecat.utils",
    "pipecat.utils.tracing",
    "pipecat.utils.tracing.setup",
    "opentelemetry",
    "opentelemetry.exporter",
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
]

for _mod in _additional_mocks:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_sessions():
    """Ensure active_sessions is empty before and after each test."""
    from agent.server import active_sessions

    active_sessions.clear()
    yield
    active_sessions.clear()


@pytest.fixture
def mock_run_bot(monkeypatch):
    """Replace run_bot with a coroutine that pushes a scripted first message."""

    async def _fake_run_bot(
        *,
        room_url,
        token,
        target_phone,
        target_who,
        goal,
        impersonate=False,
        persona=None,
        secrets=None,
        caller_id=None,
        handle_sigint=False,
        transcript_queue=None,
        on_pipeline_ready=None,
        **kwargs,
    ):
        if impersonate and persona:
            text = f"Hello {target_who}, I'm calling on behalf of {persona}."
        else:
            text = f"Hello {target_who}! I'm PATY. I'm calling to help with: {goal}."
        if transcript_queue is not None:
            await transcript_queue.put(
                {"type": "transcript", "role": "assistant", "text": text, "turn": 0}
            )

    monkeypatch.setattr("agent.server.run_bot", _fake_run_bot)


@pytest.fixture
async def client(mock_run_bot, monkeypatch):
    """Async HTTP client wired to the bot FastAPI app with auth disabled."""
    import httpx
    from httpx import ASGITransport

    import agent.server as bot_server
    from agent.server import app

    monkeypatch.setattr(bot_server, "BOT_API_KEY", "")

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
