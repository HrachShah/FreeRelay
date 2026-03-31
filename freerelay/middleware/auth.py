"""
FreeRelay — Gateway Authentication Middleware
===============================================
Optional Bearer token auth for the gateway itself.
Clients send: Authorization: Bearer <FREERELAY_API_KEY>
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Gateway-level API key authentication.
    When enabled, clients must include the gateway key as a Bearer token.
    Unauthenticated requests get a 401.

    Skip paths: /health, /ready, /dashboard, /metrics
    """

    def __init__(self, app: object, api_key: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.api_key = api_key

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for health/dashboard/metrics
        path = request.url.path
        skip_paths = ("/health", "/ready", "/dashboard", "/metrics", "/docs", "/openapi.json")
        if any(path.startswith(p) for p in skip_paths):
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == self.api_key:
                return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Invalid or missing API key. Set Authorization: Bearer <key>",
                    "type": "authentication_error",
                    "code": 401,
                }
            },
        )
