"""
FreeRelay — OpenTelemetry Tracing (§15.2)
============================================
Distributed tracing with OTLP exporter.
Falls back to no-op when OpenTelemetry is not configured.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("freerelay.shared.tracing")

_OTEL_AVAILABLE = False
_OTLP_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    pass

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    _OTLP_AVAILABLE = True
except ImportError:
    pass


# ─── No-op fallback ──────────────────────────────────────────────────────────


class _NoOpSpan:
    """No-op span when OpenTelemetry is not available."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any, description: str = "") -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    """No-op tracer when OpenTelemetry is not available."""

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Iterator[_NoOpSpan]:
        yield _NoOpSpan()


# ─── Setup ───────────────────────────────────────────────────────────────────

_tracer_provider: TracerProvider | None = None


def setup_tracing(
    service_name: str = "freerelay",
    endpoint: str | None = None,
    enabled: bool = True,
) -> None:
    """
    Configure OpenTelemetry tracing with OTLP gRPC export.

    Args:
        service_name: Service name for resource identification.
        endpoint: OTLP collector endpoint (defaults to OTEL_EXPORTER_OTLP_ENDPOINT env or localhost:4317).
        enabled: Master switch for tracing.
    """
    global _tracer_provider

    if not enabled:
        logger.info("Tracing disabled by configuration")
        return

    if not _OTEL_AVAILABLE:
        logger.warning(
            "opentelemetry-sdk not installed — tracing disabled. "
            "Install with: pip install freerelay[observability]"
        )
        return

    if not _OTLP_AVAILABLE:
        logger.warning(
            "OTLP exporter not installed — tracing will create spans but not export. "
            "Install with: pip install freerelay[observability]"
        )

    resource = Resource.create({SERVICE_NAME: service_name})
    _tracer_provider = TracerProvider(resource=resource)

    if _OTLP_AVAILABLE:
        resolved_endpoint = endpoint or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        exporter = OTLPSpanExporter(endpoint=resolved_endpoint, insecure=True)
        processor = BatchSpanProcessor(exporter)
        _tracer_provider.add_span_processor(processor)
        logger.info("OTLP tracing configured (endpoint=%s)", resolved_endpoint)

    trace.set_tracer_provider(_tracer_provider)


def get_tracer(name: str = "freerelay") -> Any:
    """
    Get a tracer instance.

    Returns a real tracer if OpenTelemetry is available,
    otherwise a no-op tracer that does nothing.
    """
    if _OTEL_AVAILABLE:
        return trace.get_tracer(name)
    return _NoOpTracer()


def shutdown_tracing() -> None:
    """Flush and shutdown the tracer provider."""
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        _tracer_provider = None
        logger.info("Tracing shut down")


# ─── Context Manager ─────────────────────────────────────────────────────────


@contextmanager
def trace_request(
    name: str,
    attributes: dict[str, Any] | None = None,
    tracer_name: str = "freerelay",
) -> Iterator[Any]:
    """
    Context manager for tracing a request span.

    Usage:
        with trace_request("route_request", {"request_id": "req_123"}) as span:
            span.set_attribute("provider", "groq")
            # ... do work ...

    Args:
        name: Span name.
        attributes: Optional span attributes.
        tracer_name: Tracer name.

    Yields:
        The span object (real or no-op).
    """
    tracer = get_tracer(tracer_name)

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                try:
                    span.set_attribute(key, value)
                except (TypeError, ValueError):
                    # OTel only accepts specific types; stringify as fallback
                    span.set_attribute(key, str(value))
        yield span


def add_workload_attributes(span: Any, workload: Any) -> None:
    """
    Add WorkloadProfile fields as span attributes.

    Args:
        span: OpenTelemetry span (or no-op span).
        workload: WorkloadProfile instance.
    """
    attrs = {
        "freerelay.request_id": workload.request_id,
        "freerelay.namespace": workload.namespace,
        "freerelay.task_family": workload.task_family.value
        if hasattr(workload.task_family, "value")
        else str(workload.task_family),
        "freerelay.depth": workload.required_depth.value
        if hasattr(workload.required_depth, "value")
        else str(workload.required_depth),
        "freerelay.latency_class": workload.latency_class.value
        if hasattr(workload.latency_class, "value")
        else str(workload.latency_class),
        "freerelay.context_topology": workload.context_topology.value
        if hasattr(workload.context_topology, "value")
        else str(workload.context_topology),
        "freerelay.output_contract": workload.output_contract.value
        if hasattr(workload.output_contract, "value")
        else str(workload.output_contract),
        "freerelay.economic_policy": workload.economic_policy.value
        if hasattr(workload.economic_policy, "value")
        else str(workload.economic_policy),
        "freerelay.prompt_tokens_est": workload.prompt_tokens_estimated,
        "freerelay.tool_count": workload.tool_count,
        "freerelay.message_count": workload.message_count,
    }
    for key, value in attrs.items():
        try:
            span.set_attribute(key, value)
        except (TypeError, ValueError):
            span.set_attribute(key, str(value))
