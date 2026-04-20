# FreeRelay Security Audit

**Date**: 2026-04-20
**Auditor**: security-expert
**Scope**: API Key System, Multi-tenant Isolation, Audit Trail

## Executive Summary
The FreeRelay platform implements several core security features including API key hashing, prefixing, and a signed audit log system. However, several critical integration gaps and potential vulnerabilities were identified during this audit, specifically regarding cache invalidation and the lack of integration of the signed audit trail.

## Findings

### 1. API Key Validation & Revocation
**File**: `freerelay/middleware/auth.py`

*   **Finding**: The `_verify_token_supabase` function is decorated with `@functools.lru_cache(maxsize=1000)`.
*   **Vulnerability**: **Stale Cache / Revocation Delay**. Once an API key is validated, it remains in the server's memory cache. If a key is deactivated or deleted in the database, the server will continue to accept it until the cache entry is evicted or the server restarts.
*   **Severity**: Medium
*   **Recommendation**: 
    1. Replace `lru_cache` with a TTL-based cache (e.g., `cachetools.TTLCache`) with a short expiration (e.g., 5-10 minutes).
    2. Implement a manual cache invalidation mechanism if the application scales.

### 2. Static Admin Key Usage
**File**: `freerelay/middleware/auth.py`

*   **Finding**: The middleware supports a static `FREERELAY_API_KEY` defined in settings.
*   **Vulnerability**: **Bypass of Multi-tenancy**. Requests using the static key are assigned `user_id = "admin"`, which may bypass certain multi-tenant filters if not handled carefully in downstream logic. Additionally, if this key is leaked, it provides full "gold" tier access to the gateway.
*   **Severity**: Medium
*   **Recommendation**: Use the static key only for internal health checks or diagnostics. Ensure production deployments rely primarily on dynamic Supabase-backed keys.

### 3. Signed Audit Trail Integration
**File**: `freerelay/shared/tenancy/audit.py`, `freerelay/middleware/audit.py`

*   **Finding**: A tamper-evident, HMAC-signed audit system is implemented in `freerelay/shared/tenancy/audit.py`, but it is **not integrated** into the gateway's `AuditMiddleware`.
*   **Issue**: Current request logging is limited to standard Python `logger.info`, which is not tamper-evident and lacks the multi-tenant namespace isolation provided by the `AuditLogger`.
*   **Severity**: Low (Functional Gap)
*   **Recommendation**: Integrate `AuditLogger` into `AuditMiddleware` to ensure all requests are signed and stored in a tenant-isolated stream (e.g., Redis).

### 4. Multi-tenant Isolation in Analytics/Requests
**File**: `freerelay/main.py` (and anticipated endpoints)

*   **Observation**: The `/v1/analytics` and `/v1/requests` endpoints (as described in the task board) must strictly enforce isolation.
*   **Audit Status**: **Blocked**. Code for these endpoints was not present in the repository at the time of audit.
*   **Requirements for Security**:
    1. Endpoints MUST fetch the `user_id` from `request.state`.
    2. Database queries MUST explicitly filter by `user_id`.
    3. User-supplied IDs in query parameters MUST NOT be used for data retrieval unless they match the authenticated `user_id`.

## Security Best Practices for FreeRelay
1. **Secret Scanning**: Enable GitHub secret scanning for the `fr_` prefix.
2. **Environment Variables**: Never commit `.env` files. Ensure `.env.example` is kept up to date without real secrets.
3. **Dependency Updates**: Regularly audit `requirements.txt` for vulnerable packages (e.g., using `safety` or `pip-audit`).
