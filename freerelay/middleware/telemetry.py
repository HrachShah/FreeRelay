"""
FreeRelay — OpenTelemetry Middleware (§16.2)
===============================================
Injects OpenTelemetry spans for request tracing.
Creates root span and injects trace-id into request context.
"""

from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("freerelay.telemetry")

_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    pass


class TelemetryMiddleware(BaseHTTPMiddleware):
    """
    OpenTelemetry span injection middleware.

    Creates a root span for every request and adds
    standard attributes (request_id, path, method, status).
    """

    def __init__(self, app: object, enabled: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.enabled = enabled and _OTEL_AVAILABLE
        self._tracer = trace.get_tracer("freerelay") if self.enabled else None  # type: ignore[name-defined]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self.enabled or not self._tracer:
            return await call_next(request)

        with self._tracer.start_as_current_span("freerelay.request") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.path", request.url.path)

            start = time.time()
            try:
                response = await call_next(request)
                elapsed_ms = (time.time() - start) * 1000

                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("duration_ms", round(elapsed_ms, 1))

                if response.status_code >= 400:
                    span.set_status(StatusCode.ERROR)  # type: ignore[name-defined]
                else:
                    span.set_status(StatusCode.OK)  # type: ignore[name-defined]

                return response

            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                span.set_attribute("duration_ms", round(elapsed_ms, 1))
                span.set_status(StatusCode.ERROR, str(e))  # type: ignore[name-defined]
                span.record_exception(e)
                raise