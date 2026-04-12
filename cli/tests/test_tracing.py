"""Tests for OpenTelemetry tracing setup using a simple in-memory exporter."""

from __future__ import annotations

import threading

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from paty.config.schema import TracingConfig
from paty.tracing.setup import setup_tracing


class MemoryExporter(SpanExporter):
    """Minimal in-memory exporter for testing."""

    def __init__(self):
        self._spans = []
        self._lock = threading.Lock()

    def export(self, spans):
        with self._lock:
            self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def get_finished_spans(self):
        with self._lock:
            return list(self._spans)

    def shutdown(self):
        pass


def _reset_tracer_provider():
    """Reset the global tracer provider between tests."""
    trace.set_tracer_provider(TracerProvider())


class TestSetupTracing:
    def setup_method(self):
        _reset_tracer_provider()

    def teardown_method(self):
        _reset_tracer_provider()

    def test_returns_tracer(self):
        config = TracingConfig(enabled=True, console=False)
        tracer = setup_tracing(config)
        assert tracer is not None

    def test_spans_are_recorded(self):
        config = TracingConfig(enabled=True, console=False)
        tracer = setup_tracing(config)

        provider = trace.get_tracer_provider()
        exporter = MemoryExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with tracer.start_as_current_span("paty.startup") as span:
            span.set_attribute("paty.config_path", "test.yaml")
            with tracer.start_as_current_span("paty.hardware.detect") as hw_span:
                hw_span.set_attribute("paty.platform", "mlx")

        spans = exporter.get_finished_spans()
        span_names = [s.name for s in spans]
        assert "paty.hardware.detect" in span_names
        assert "paty.startup" in span_names

    def test_startup_span_has_child(self):
        config = TracingConfig(enabled=True, console=False)
        tracer = setup_tracing(config)

        provider = trace.get_tracer_provider()
        exporter = MemoryExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with (
            tracer.start_as_current_span("paty.startup"),
            tracer.start_as_current_span("paty.hardware.detect"),
        ):
            pass

        spans = exporter.get_finished_spans()
        startup = next(s for s in spans if s.name == "paty.startup")
        hw = next(s for s in spans if s.name == "paty.hardware.detect")

        assert hw.parent is not None
        assert hw.parent.span_id == startup.context.span_id

    def test_disabled_tracing_still_works(self):
        config = TracingConfig(enabled=False, console=False)
        tracer = setup_tracing(config)
        with tracer.start_as_current_span("paty.test"):
            pass
