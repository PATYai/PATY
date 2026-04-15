"""OpenTelemetry MeterProvider initialization and Rich console exporter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    MetricExporter,
    MetricExportResult,
    MetricsData,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from rich.console import Console
from rich.table import Table

from paty import __version__
from paty.metrics.observer import PipelineMetricsObserver

if TYPE_CHECKING:
    from paty.config.schema import MetricsConfig
    from paty.dashboard.collectors import RollingCollector

# Histogram metric names and their display labels
_HISTOGRAM_DISPLAY = {
    "paty_stt_ttfb_seconds": "STT TTFB",
    "paty_llm_ttfb_seconds": "LLM TTFB",
    "paty_tts_ttfb_seconds": "TTS TTFB",
    "paty_llm_processing_seconds": "LLM Processing",
}

_COUNTER_DISPLAY = {
    "paty_llm_tokens_total": "LLM Tokens",
    "paty_tts_characters_total": "TTS Characters",
}

_console = Console()


def _format_ms(seconds: float) -> str:
    """Format seconds as milliseconds with 0 decimal places."""
    return f"{seconds * 1000:.0f}ms"


class RichMetricsExporter(MetricExporter):
    """Exports OTEL metrics as a Rich table to the console."""

    def __init__(self, console: Console | None = None):
        super().__init__()
        self._console = console or _console

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs,
    ) -> MetricExportResult:
        histograms: dict[str, dict] = {}
        counters: dict[str, int] = {}

        for resource_metrics in metrics_data.resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    name = metric.name
                    if name in _HISTOGRAM_DISPLAY:
                        # Aggregate across all data points
                        for dp in metric.data.data_points:
                            entry = histograms.setdefault(
                                name,
                                {
                                    "count": 0,
                                    "sum": 0.0,
                                    "min": float("inf"),
                                    "max": 0.0,
                                },
                            )
                            entry["count"] += dp.count
                            entry["sum"] += dp.sum
                            if dp.min is not None:
                                entry["min"] = min(entry["min"], dp.min)
                            if dp.max is not None:
                                entry["max"] = max(entry["max"], dp.max)

                    elif name in _COUNTER_DISPLAY:
                        for dp in metric.data.data_points:
                            label = name
                            # Include type attribute for token counters
                            token_type = dict(dp.attributes).get("type")
                            if token_type:
                                label = f"{name}:{token_type}"
                            counters[label] = counters.get(label, 0) + dp.value

        # Skip if no data yet
        if not histograms and not counters:
            return MetricExportResult.SUCCESS

        table = Table(title="PATY Performance", expand=False)
        table.add_column("Metric", style="bold")
        table.add_column("avg", justify="right")
        table.add_column("min", justify="right")
        table.add_column("max", justify="right")
        table.add_column("count", justify="right")

        for name, display_name in _HISTOGRAM_DISPLAY.items():
            data = histograms.get(name)
            if data and data["count"] > 0:
                avg = data["sum"] / data["count"]
                table.add_row(
                    display_name,
                    _format_ms(avg),
                    _format_ms(data["min"]),
                    _format_ms(data["max"]),
                    str(data["count"]),
                )

        if counters:
            table.add_section()
            # LLM tokens
            prompt = counters.get("paty_llm_tokens_total:prompt", 0)
            completion = counters.get("paty_llm_tokens_total:completion", 0)
            if prompt or completion:
                table.add_row(
                    "LLM Tokens",
                    f"prompt: {prompt:,}",
                    "",
                    f"comp: {completion:,}",
                    "",
                )
            tts = counters.get("paty_tts_characters_total", 0)
            if tts:
                table.add_row("TTS Characters", f"{tts:,}", "", "", "")

        self._console.print(table)
        return MetricExportResult.SUCCESS

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True


class MetricsHandle:
    """Returned by setup_metrics; holds references needed by the pipeline."""

    def __init__(
        self,
        meter: metrics.Meter,
        observer: PipelineMetricsObserver,
        in_memory_reader: InMemoryMetricReader,
    ):
        self.meter = meter
        self.observer = observer
        self.in_memory_reader = in_memory_reader


def setup_metrics(
    config: MetricsConfig,
    collector: RollingCollector | None = None,
) -> MetricsHandle:
    """Initialize the global OTEL MeterProvider and return a MetricsHandle.

    The handle contains the PipelineMetricsObserver to attach to the
    Pipecat PipelineTask and an InMemoryMetricReader for programmatic access.

    When *collector* is provided, raw metric values are also recorded into it
    for percentile computation by dashboard frontends.
    """
    resource = Resource.create(
        {
            "service.name": "paty",
            "service.version": __version__,
        }
    )

    readers: list = []

    # Always create an in-memory reader for programmatic access
    in_memory_reader = InMemoryMetricReader()
    readers.append(in_memory_reader)

    if config.enabled and config.console_interval > 0:
        rich_reader = PeriodicExportingMetricReader(
            RichMetricsExporter(),
            export_interval_millis=config.console_interval * 1000,
        )
        readers.append(rich_reader)

    if config.enabled and config.prometheus:
        try:
            from opentelemetry.exporter.prometheus import PrometheusMetricReader

            prom_reader = PrometheusMetricReader()
            readers.append(prom_reader)

            # PrometheusMetricReader starts its own HTTP server on 9464 by default.
            # To customize the port, start prometheus_client manually.
            if config.prometheus_port != 9464:
                from prometheus_client import start_http_server

                start_http_server(config.prometheus_port)

        except ImportError:
            _console.print(
                "[yellow]metrics.prometheus=true but opentelemetry-exporter-prometheus "
                "not installed. Install with: pip install paty[prometheus][/]"
            )

    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("paty")
    observer = PipelineMetricsObserver(meter=meter, collector=collector)

    return MetricsHandle(
        meter=meter,
        observer=observer,
        in_memory_reader=in_memory_reader,
    )
