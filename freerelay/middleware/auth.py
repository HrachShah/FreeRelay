"""
FreeRelay — Gateway Authentication Middleware
===============================================
Optional Bearer token auth for the gateway itself.
Clients send: Authorization: Bearer <FREERELAY_API_KEY>
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from freerelay.shared.security.crypto import hash_api_key

logger = logging.getLogger("freerelay.auth")

@functools.lru_cache(maxsize=1000)
def _verify_token_team_db(token_hash: str) -> dict[str, str] | None:
    """
    Verify a token hash against team-db api_keys table.
    """
    import subprocess
    import json
    try:
        # Join with organizations to get the tier
        sql = f"""
        SELECT 
            api_keys.user_id, 
            api_keys.org_id, 
            organizations.tier 
        FROM api_keys 
        JOIN organizations ON api_keys.org_id = organizations.id 
        WHERE key_hash = '{token_hash}' AND is_active = 1
        """
        result = subprocess.run(["team-db", sql.strip()], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        if data:
            return {
                "user_id": data[0]["user_id"], 
                "org_id": data[0]["org_id"],
                "tier": data[0]["tier"]
            }
        return None
    except Exception as e:
        logger.error(f"Team-db auth error: {e}")
        return None

@functools.lru_cache(maxsize=1000)
def _verify_token_supabase(token_hash: str) -> dict[str, str] | None:
    """
    Verify a token hash against Supabase api_keys table.
    Cached to avoid repeated DB calls.
    Returns a dict with user_id, org_id and tier if valid, else None.
    """
    from freerelay.shared.tenancy.supabase import get_supabase_client
    try:
        supabase = get_supabase_client()
        # Join with organizations table to get the tier
        result = (
            supabase.table("api_keys")
            .select("user_id, org_id, organizations(tier)")
            .eq("key_hash", token_hash)
            .eq("is_active", True)
            .execute()
        )
        if result.data:
            data: Any = result.data[0]
            user_id = str(data["user_id"])
            org_id = str(data["org_id"])
            org_data: Any = data.get("organizations")
            tier = "free"
            if isinstance(org_data, dict):
                tier = str(org_data.get("tier", "free"))
            return {"user_id": user_id, "org_id": org_id, "tier": tier}
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
                request.state.org_id = "admin_org"
                request.state.tier = "gold"
                return await call_next(request)

            # 2. Supabase check
            if self.enable_supabase:
                token_hash = hash_api_key(token)
                user_info = _verify_token_supabase(token_hash)
                if user_info:
                    request.state.user_id = user_info["user_id"]
                    request.state.org_id = user_info["org_id"]
                    request.state.tier = user_info["tier"]
                    return await call_next(request)

            # 3. Team-db check (fallback or alternative)
            token_hash = hash_api_key(token)
            user_info = _verify_token_team_db(token_hash)
            if user_info:
                request.state.user_id = user_info["user_id"]
                request.state.org_id = user_info["org_id"]
                request.state.tier = user_info["tier"]
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
