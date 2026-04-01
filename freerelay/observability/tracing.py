"""
FreeRelay — OpenTelemetry Tracing (§16.2)
============================================
OTLP exporter for distributed tracing.
Sends spans to Jaeger or any OTLP-compatible backend.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("freerelay.tracing")

_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    _OTLP_AVAILABLE = True
except ImportError:
    _OTLP_AVAILABLE = False


def setup_tracing(
    service_name: str = "freerelay",
    endpoint: str = "http://localhost:4317",
    enabled: bool = True,
) -> None:
    """
    Configure OpenTelemetry tracing with OTLP export.

    Args:
        service_name: Name of the service for traces.
        endpoint: OTLP collector endpoint (gRPC).
        enabled: Whether to enable tracing.
    """
    if not enabled:
        return

    if not _SDK_AVAILABLE:
        logger.warning("opentelemetry-sdk not installed — tracing disabled")
        return

    if not _OTLP_AVAILABLE:
        logger.warning("OTLP exporter not installed — tracing disabled")
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing configured (endpoint=%s)", endpoint)


def get_tracer(name: str = "freerelay") -> object:
    """Get a tracer instance."""
    if _SDK_AVAILABLE:
        return trace.get_tracer(name)
    return _NoOpTracer()


class _NoOpTracer:
    """No-op tracer when OpenTelemetry is not available."""

    def start_as_current_span(self, name: str) -> object:
        return _NoOpSpan()


class _NoOpSpan:
    """No-op span."""

    def __enter__(self) -> object:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def set_attribute(self, key: str, value: object) -> None:
        pass

    def set_status(self, status: object, description: str = "") -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass
