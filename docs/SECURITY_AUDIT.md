# FreeRelay Security Audit

**Date**: 2026-04-20
**Auditor**: security-expert
**Scope**: API Key System, Multi-tenant Isolation, Audit Trail, Registration

## Executive Summary
The FreeRelay platform implements core security features like API key hashing and signed audit logs. However, critical vulnerabilities exist in the registration flow (account hijacking) and the API key validation cache. Additionally, the signed audit trail is currently unimplemented in the main request flow.

## Findings

### 1. Account Hijacking via Registration (High Risk)
**File**: `freerelay/main.py`

*   **Finding**: The `/v1/auth/register` endpoint uses `upsert` on the `email` column.
*   **Vulnerability**: An attacker can register using an existing user's email. The system will retrieve the existing `user_id` and generate a new API key for the attacker, giving them full access to the victim's account and logs.
*   **Severity**: High
*   **Recommendation**: Change `upsert` to `insert` to prevent re-registration of existing emails. Implement email verification.

### 2. API Key Revocation Delay (Medium Risk)
**File**: `freerelay/middleware/auth.py`

*   **Finding**: API key validation was previously using `functools.lru_cache`.
*   **Vulnerability**: Stale cache entries allowed deactivated keys to remain active until eviction.
*   **Status**: **Fixed**. I have replaced the LRU cache with a 60-second TTL cache in `AuthMiddleware`.

### 3. Static Admin Key (Medium Risk)
**File**: `freerelay/middleware/auth.py`

*   **Finding**: Supports a static `FREERELAY_API_KEY` granting full "gold" access as "admin".
*   **Vulnerability**: Bypasses multi-tenant isolation. Leakage would grant full system access.
*   **Recommendation**: Restrict to internal use/diagnostics only.

### 4. Signed Audit Trail Integration Gap (Low Risk)
**File**: `freerelay/shared/tenancy/audit.py`, `freerelay/middleware/audit.py`

*   **Finding**: A signed audit system exists but isn't used in the request middleware.
*   **Recommendation**: Replace basic `AuditMiddleware` with the signed `AuditLogger` for tamper-evident logs.

### 5. Multi-tenant Isolation in Analytics/Requests
**File**: `freerelay/main.py`

*   **Audit Status**: **Blocked**. Code for `/v1/analytics` and `/v1/requests` was not present in the repository at the time of audit.
