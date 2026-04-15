"""Central provider that assembles DashboardSnapshot from all data sources."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from paty.dashboard.audio_observer import AudioLevelObserver
from paty.dashboard.collectors import RollingCollector
from paty.dashboard.snapshot import AudioLevels, DashboardSnapshot, StageMetrics

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

# Metric names matching those in paty.metrics.observer
_STAGE_METRICS = {
    "stt": "paty_stt_ttfb_seconds",
    "llm_ttfb": "paty_llm_ttfb_seconds",
    "tts": "paty_tts_ttfb_seconds",
}

_COUNTER_NAMES = {
    "llm_tokens": "paty_llm_tokens_total",
    "tts_chars": "paty_tts_characters_total",
}


def _to_ms(val: float | None) -> float | None:
    return val * 1000.0 if val is not None else None


def _read_counters(reader: InMemoryMetricReader) -> dict[str, int]:
    """Extract counter totals from the OTEL in-memory reader."""
    counters: dict[str, int] = {}
    data = reader.get_metrics_data()
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name in _COUNTER_NAMES.values():
                    for dp in metric.data.data_points:
                        label = metric.name
                        token_type = dict(dp.attributes).get("type")
                        if token_type:
                            label = f"{metric.name}:{token_type}"
                        counters[label] = counters.get(label, 0) + dp.value
    return counters


class DashboardProvider:
    """Owns data sources and yields snapshots for any frontend.

    Usage::

        provider = DashboardProvider()
        # Pass provider.collector to PipelineMetricsObserver
        # Pass provider.audio_observer to the PipelineTask observers list
        snapshot = provider.snapshot(metrics_reader)
    """

    def __init__(self, window_size: int = 200):
        self.collector = RollingCollector(window_size=window_size)
        self.audio_observer = AudioLevelObserver()
        self._start_time = time.monotonic()

    def _stage(self, metric_name: str) -> StageMetrics:
        return StageMetrics(
            avg_ms=_to_ms(self.collector.avg(metric_name)),
            p95_ms=_to_ms(self.collector.percentile(metric_name, 95)),
            max_ms=_to_ms(self.collector.max_val(metric_name)),
            count=self.collector.count(metric_name),
        )

    def snapshot(
        self, metrics_reader: InMemoryMetricReader | None = None
    ) -> DashboardSnapshot:
        counters: dict[str, int] = {}
        if metrics_reader is not None:
            counters = _read_counters(metrics_reader)

        return DashboardSnapshot(
            stt=self._stage(_STAGE_METRICS["stt"]),
            llm_ttfb=self._stage(_STAGE_METRICS["llm_ttfb"]),
            tts=self._stage(_STAGE_METRICS["tts"]),
            audio=AudioLevels(
                bands=list(self.audio_observer.levels.bands),
                rms=self.audio_observer.levels.rms,
                timestamp=self.audio_observer.levels.timestamp,
            ),
            llm_tokens_prompt=counters.get(f"{_COUNTER_NAMES['llm_tokens']}:prompt", 0),
            llm_tokens_completion=counters.get(
                f"{_COUNTER_NAMES['llm_tokens']}:completion", 0
            ),
            tts_characters=counters.get(_COUNTER_NAMES["tts_chars"], 0),
            uptime_seconds=time.monotonic() - self._start_time,
        )
