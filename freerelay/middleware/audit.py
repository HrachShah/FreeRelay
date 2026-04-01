"""
FreeRelay — Audit Trail Middleware
====================================
Logs every request/response pair for debugging and compliance.
"""

from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("freerelay.audit")


class AuditMiddleware(BaseHTTPMiddleware):
    """Log request metadata for every API call."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000

        # Only audit API routes
        if request.url.path.startswith("/v1/"):
            logger.info(
                "audit",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": round(elapsed_ms, 1),
                    "client": request.client.host if request.client else "unknown",
                    "user_agent": request.headers.get("user-agent", "")[:100],
                },
            )

        return response
