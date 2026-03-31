"""
FreeRelay Data Plane — Request Telemetry (§16)
=================================================
OpenTelemetry span creation with trace-id injection.
Adds WorkloadProfile as span attributes for routing analysis.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from freerelay.data_plane.profiler.workload import WorkloadProfile

logger = logging.getLogger("freerelay.data_plane.telemetry")

# Graceful degradation: if opentelemetry is not installed, use no-op spans
try:
    from opentelemetry import trace
    from opentelemetry.trace import Span, SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    trace = None  # type: ignore[assignment]
    Span = Any  # type: ignore[misc, assignment]
    SpanKind = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]
    TraceContextTextMapPropagator = None  # type: ignore[assignment]


_TRACER_NAME = "freerelay.data_plane"


def _get_tracer() -> Any:
    """Get the OpenTelemetry tracer, or None if unavailable."""
    if not _OTEL_AVAILABLE or trace is None:
        return None
    return trace.get_tracer(_TRACER_NAME)


class _NoOpSpan:
    """No-op span for when OpenTelemetry is not available."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@contextmanager
def create_request_span(
    request_id: str,
    namespace: str,
    profile: WorkloadProfile | None = None,
    attributes: dict[str, Any] | None = None,
) -> Generator[Span | _NoOpSpan, None, None]:
    """
    Create an OpenTelemetry span for a request.

    Injects trace-id into the context and attaches WorkloadProfile attributes.

    Args:
        request_id: Unique request identifier.
        namespace: Tenant namespace.
        profile: Optional WorkloadProfile to attach as span attributes.
        attributes: Additional span attributes.

    Yields:
        An OpenTelemetry Span (or no-op if OTel not available).
    """
    tracer = _get_tracer()

    if tracer is None:
        span = _NoOpSpan()
        span.set_attribute("request_id", request_id)
        span.set_attribute("namespace", namespace)
        try:
            yield span
        finally:
            span.end()
        return

    with tracer.start_as_current_span(
        "data_plane.request",
        kind=SpanKind.INTERNAL,
    ) as span:
        span.set_attribute("request_id", request_id)
        span.set_attribute("namespace", namespace)
        span.set_attribute("service.name", "freerelay-data-plane")

        if profile is not None:
            _attach_profile(span, profile)

        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def _attach_profile(span: Span, profile: WorkloadProfile) -> None:
    """Attach WorkloadProfile fields as span attributes."""
    span.set_attribute("workload.task_family", profile.task_family)
    span.set_attribute("workload.required_depth", profile.required_depth)
    span.set_attribute("workload.precision_sensitivity", profile.precision_sensitivity)
    span.set_attribute("workload.latency_class", profile.latency_class)
    span.set_attribute("workload.context_topology", profile.context_topology)
    span.set_attribute("workload.tool_dependence", profile.tool_dependence)
    span.set_attribute("workload.determinism_needs", profile.determinism_needs)
    span.set_attribute("workload.safety_posture", profile.safety_posture)
    span.set_attribute("workload.output_contract", profile.output_contract)
    span.set_attribute("workload.economic_policy", profile.economic_policy)
    span.set_attribute("workload.estimated_tokens", profile.estimated_tokens)
    span.set_attribute("workload.message_count", profile.message_count)


def inject_trace_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Inject current trace context into HTTP headers for downstream propagation.

    Args:
        headers: Existing headers dict (mutated and returned).

    Returns:
        The headers dict with traceparent injected.
    """
    if not _OTEL_AVAILABLE or TraceContextTextMapPropagator is None:
        return headers

    try:
        propagator = TraceContextTextMapPropagator()
        propagator.inject(headers)
    except Exception:
        logger.debug("Failed to inject trace headers", exc_info=True)

    return headers


def extract_trace_context(headers: dict[str, str]) -> Any:
    """
    Extract trace context from incoming HTTP headers.

    Args:
        headers: HTTP headers dict.

    Returns:
        OpenTelemetry Context object, or empty context.
    """
    if not _OTEL_AVAILABLE or TraceContextTextMapPropagator is None:
        return {}

    try:
        propagator = TraceContextTextMapPropagator()
        return propagator.extract(headers)
    except Exception:
        logger.debug("Failed to extract trace context", exc_info=True)
        return {}
