"""
FreeRelay — Gateway Authentication Middleware
===============================================
Optional Bearer token auth for the gateway itself.
Clients send: Authorization: Bearer <FREERELAY_API_KEY>
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from freerelay.shared.security.crypto import hash_api_key

logger = logging.getLogger("freerelay.auth")

# Simple TTL Cache for auth tokens to ensure revocation is respected within 60s
_AUTH_CACHE: dict[str, tuple[dict[str, str], float]] = {}
_CACHE_TTL = 60.0  # 60 seconds

def _verify_token_supabase(token_hash: str) -> dict[str, str] | None:
    """
    Verify a token hash against Supabase api_keys table.
    Uses a manual TTL cache to allow for relatively fast revocation.
    Returns a dict with user_id and tier if valid, else None.
    """
    now = time.time()
    if token_hash in _AUTH_CACHE:
        data, expiry = _AUTH_CACHE[token_hash]
        if now < expiry:
            return data
        else:
            del _AUTH_CACHE[token_hash]

    from freerelay.shared.tenancy.supabase import get_supabase_client
    try:
        supabase = get_supabase_client()
        # Join with users table to get the tier
        result = (
            supabase.table("api_keys")
            .select("user_id, users(tier, routing_preference)")
            .eq("key_hash", token_hash)
            .eq("is_active", True)
            .execute()
        )
        if result.data:
            data_res: Any = result.data[0]
            user_id = str(data_res["user_id"])
            users_data: Any = data_res.get("users")
            tier = "free"
            routing_preference = "balanced"
            if isinstance(users_data, dict):
                tier = str(users_data.get("tier", "free"))
                routing_preference = str(users_data.get("routing_preference", "balanced"))
            
            user_info = {
                "user_id": user_id, 
                "tier": tier, 
                "routing_preference": routing_preference
            }
            _AUTH_CACHE[token_hash] = (user_info, now + _CACHE_TTL)
            return user_info
        return None
    except Exception as e:
        logger.error(f"Supabase auth error: {e}")
        return None

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
        # Skip auth for health/dashboard/metrics/registration/checkout/webhooks
        path = request.url.path
        skip_paths = (
            "/health", "/ready", "/dashboard", "/metrics", "/docs", 
            "/openapi.json", "/v1/auth/register", "/v1/billing/checkout",
            "/v1/billing/webhook"
        )
        if any(path.startswith(p) for p in skip_paths) or path == "/":
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
            # 1. Static key check
            if self.api_key and token == self.api_key:
                request.state.user_id = "admin"
                request.state.tier = "gold"
                request.state.routing_preference = "balanced"
                return await call_next(request)
            
            # 2. Supabase check
            if self.enable_supabase:
                token_hash = hash_api_key(token)
                user_info = _verify_token_supabase(token_hash)
                if user_info:
                    request.state.user_id = user_info["user_id"]
                    request.state.tier = user_info["tier"]
                    request.state.routing_preference = user_info["routing_preference"]
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
