"""OpenTelemetry TracerProvider initialization.

Sets up a global TracerProvider that both PATY and Pipecat share.
Pipecat's built-in OTel tracing automatically inherits this provider,
so all spans (startup + conversation) export to the same backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from paty import __version__

if TYPE_CHECKING:
    from paty.config.schema import TracingConfig


def setup_tracing(config: TracingConfig) -> trace.Tracer:
    """Initialize the global OpenTelemetry TracerProvider.

    Always creates a provider so span calls are no-ops (not errors)
    even when no exporter is configured.
    """
    resource = Resource.create(
        {
            "service.name": config.service_name,
            "service.version": __version__,
        }
    )
    provider = TracerProvider(resource=resource)

    if config.enabled:
        if config.console:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        if config.otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=config.otlp_endpoint,
                        insecure=True,
                    )
                )
            )

    trace.set_tracer_provider(provider)
    return trace.get_tracer("paty")
