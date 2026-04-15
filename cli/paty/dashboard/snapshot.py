"""Frozen-in-time dashboard state consumed by any frontend."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StageMetrics:
    """Latency stats for a single pipeline stage."""

    avg_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None
    count: int = 0


@dataclass
class AudioLevels:
    """Real-time audio frequency bands and RMS level."""

    bands: list[float] = field(default_factory=lambda: [0.0] * 8)
    rms: float = 0.0
    timestamp: float = 0.0


@dataclass(frozen=True)
class DashboardSnapshot:
    """Single poll of all dashboard data — GUI-agnostic."""

    stt: StageMetrics = field(default_factory=StageMetrics)
    llm_ttfb: StageMetrics = field(default_factory=StageMetrics)
    tts: StageMetrics = field(default_factory=StageMetrics)
    audio: AudioLevels = field(default_factory=AudioLevels)
    llm_tokens_prompt: int = 0
    llm_tokens_completion: int = 0
    tts_characters: int = 0
    uptime_seconds: float = 0.0
