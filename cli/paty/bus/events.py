"""Event envelope and typed payload models for the PATY bus."""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel

PROTOCOL_VERSION = 1


class EventType(StrEnum):
    # Session lifecycle
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"

    # User turn
    USER_SPEECH_STARTED = "user.speech_started"
    USER_SPEECH_STOPPED = "user.speech_stopped"
    USER_TRANSCRIPT_PARTIAL = "user.transcript.partial"
    USER_TRANSCRIPT_FINAL = "user.transcript.final"

    # Agent turn
    AGENT_THINKING_STARTED = "agent.thinking_started"
    AGENT_RESPONSE_DELTA = "agent.response.delta"
    AGENT_RESPONSE_COMPLETED = "agent.response.completed"
    AGENT_SPEECH_STARTED = "agent.speech_started"
    AGENT_SPEECH_STOPPED = "agent.speech_stopped"

    # Derived state + ops
    STATE_CHANGED = "state.changed"
    METRICS_TICK = "metrics.tick"
    ERROR = "error"
    LOG = "log"


class AgentState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class AudioStream(IntEnum):
    """Stream identifier carried in the binary audio header."""

    MIC = 1
    AGENT = 2


class Event(BaseModel):
    """Wire envelope for a control event."""

    v: int = PROTOCOL_VERSION
    seq: int
    ts_ms: int
    session_id: str
    type: EventType
    data: dict[str, Any]


# --- Typed payloads (optional; pass-through to `data` dict via model_dump) ---


class SessionStarted(BaseModel):
    persona: str
    profile: str
    platform: str
    stt: str
    llm: str
    tts: str
    sample_rate_in: int | None = None
    sample_rate_out: int | None = None


class SessionEnded(BaseModel):
    reason: str


class SpeechStopped(BaseModel):
    duration_ms: int | None = None


class Transcript(BaseModel):
    text: str


class ResponseCompleted(BaseModel):
    text: str


class StateChanged(BaseModel):
    state: AgentState


class MetricsTick(BaseModel):
    ttfb_ms: float | None = None
    stt_ms: float | None = None
    llm_ms: float | None = None
    tts_ms: float | None = None
    processor: str | None = None


class ErrorData(BaseModel):
    message: str
    recoverable: bool = True


class LogData(BaseModel):
    level: str
    module: str
    message: str
