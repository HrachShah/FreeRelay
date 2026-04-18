"""
FreeRelay — Gateway Authentication Middleware
===============================================
Optional Bearer token auth for the gateway itself.
Clients send: Authorization: Bearer <FREERELAY_API_KEY>
"""

from __future__ import annotations

import functools
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from freerelay.shared.security.crypto import hash_api_key

logger = logging.getLogger("freerelay.auth")

@functools.lru_cache(maxsize=1000)
def _verify_token_supabase(token_hash: str) -> bool:
    """
    Verify a token hash against Supabase api_keys table.
    Cached to avoid repeated DB calls.
    """
    from freerelay.shared.tenancy.supabase import get_supabase_client
    try:
        supabase = get_supabase_client()
        query = supabase.table("api_keys").select("id").eq("key_hash", token_hash)
        result = query.execute()
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Supabase auth error: {e}")
        return False

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Gateway-level API key authentication.
    Supports both a static FREERELAY_API_KEY and Supabase-backed dynamic keys.
    """

    def __init__(
        self, app: object, api_key: str = "", enable_supabase: bool = False
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.api_key = api_key
        self.enable_supabase = enable_supabase

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for health/dashboard/metrics/registration
        path = request.url.path
        skip_paths = (
            "/health", "/ready", "/dashboard", "/metrics", "/docs", 
            "/openapi.json", "/v1/auth/register", "/v1/billing/checkout"
        )
        if any(path.startswith(p) for p in skip_paths) or path == "/":
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
            # 1. Static key check
            if self.api_key and token == self.api_key:
                return await call_next(request)
            
            # 2. Supabase check
            if self.enable_supabase:
                token_hash = hash_api_key(token)
                if _verify_token_supabase(token_hash):
                    return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Invalid or missing API key.",
                    "type": "authentication_error",
                    "code": 401,
                }
            },
        )
