"""Pipecat observer that records pipeline metrics into OpenTelemetry instruments."""

from __future__ import annotations

from opentelemetry import metrics
from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    ProcessingMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

_SERVICE_KEYWORDS = {
    "stt": ("stt", "whisper", "assemblyai", "deepgram"),
    "llm": ("llm", "openai", "ollama", "llama"),
    "tts": ("tts", "cartesia", "kokoro", "mlxaudio"),
}


def _classify_processor(processor: str) -> str:
    """Classify a processor name as stt/llm/tts based on keywords."""
    lower = processor.lower()
    for category, keywords in _SERVICE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "unknown"


class PipelineMetricsObserver(BaseObserver):
    """Captures Pipecat MetricsFrames and records them as OTEL metrics.

    Instruments created:
        - paty_stt_ttfb_seconds (Histogram)
        - paty_llm_ttfb_seconds (Histogram)
        - paty_tts_ttfb_seconds (Histogram)
        - paty_llm_processing_seconds (Histogram)
        - paty_llm_tokens_total (Counter)
        - paty_tts_characters_total (Counter)
    """

    def __init__(self, meter: metrics.Meter | None = None, **kwargs):
        super().__init__(**kwargs)
        m = meter or metrics.get_meter("paty")

        self._ttfb = {
            "stt": m.create_histogram(
                "paty_stt_ttfb_seconds",
                description="STT time to first byte",
                unit="s",
            ),
            "llm": m.create_histogram(
                "paty_llm_ttfb_seconds",
                description="LLM time to first byte",
                unit="s",
            ),
            "tts": m.create_histogram(
                "paty_tts_ttfb_seconds",
                description="TTS time to first byte",
                unit="s",
            ),
        }

        self._processing = m.create_histogram(
            "paty_llm_processing_seconds",
            description="LLM total processing time",
            unit="s",
        )

        self._llm_tokens = m.create_counter(
            "paty_llm_tokens_total",
            description="LLM token usage",
        )

        self._tts_chars = m.create_counter(
            "paty_tts_characters_total",
            description="TTS characters synthesized",
        )

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if not isinstance(frame, MetricsFrame):
            return

        for entry in frame.data:
            attrs = {"processor": entry.processor}
            if entry.model:
                attrs["model"] = entry.model

            if isinstance(entry, TTFBMetricsData):
                category = _classify_processor(entry.processor)
                histogram = self._ttfb.get(category)
                if histogram:
                    histogram.record(entry.value, attrs)

            elif isinstance(entry, ProcessingMetricsData):
                self._processing.record(entry.value, attrs)

            elif isinstance(entry, LLMUsageMetricsData):
                usage = entry.value
                if hasattr(usage, "prompt_tokens") and usage.prompt_tokens:
                    self._llm_tokens.add(
                        usage.prompt_tokens, {**attrs, "type": "prompt"}
                    )
                if hasattr(usage, "completion_tokens") and usage.completion_tokens:
                    self._llm_tokens.add(
                        usage.completion_tokens, {**attrs, "type": "completion"}
                    )

            elif isinstance(entry, TTSUsageMetricsData):
                self._tts_chars.add(entry.value, attrs)
