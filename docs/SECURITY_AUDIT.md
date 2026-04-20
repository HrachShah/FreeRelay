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
*   **Status**: **Fixed**. I have replaced `upsert` with a strict `insert` in `/v1/auth/register` to prevent account hijacking.
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

### 5. Inconsistent Tenancy Filtering & Data Leak Risk (High Risk)
**File**: `freerelay/observability/analytics.py`, `freerelay/main.py`

*   **Finding**: The `/v1/analytics` endpoint passes `user_id` to `get_usage_analytics`, which then queries the `org_id` column in the database.
*   **Vulnerability**: 
    1. **Data Inaccessibility**: Users cannot see their own data because it's stored under `user_id` but queried via `org_id`.
    2. **Data Leak**: If the `org_id` parameter is missing or null, the query falls back to `WHERE (org_id IS NULL OR org_id = '')`. This returns ALL records without an organization ID, potentially leaking usage data from multiple users to any authenticated requester who lacks an `org_id` in their profile.
*   **Severity**: High
*   **Recommendation**: 
    1. Standardize on either `user_id` or `org_id` across the entire stack (Auth, Logging, Analytics).
    2. Ensure that `get_usage_analytics` NEVER falls back to returning all records if the ID is missing; it should return an empty set or raise an error.

### 6. SQL Injection Vulnerability (High Risk)
**File**: `freerelay/observability/analytics.py`

*   **Finding**: Database queries are constructed using f-strings and executed via `subprocess.run(["team-db", query], ...)`.
*   **Vulnerability**: **SQL Injection**. While the `org_id` currently comes from the authenticated request state, any future change that allows user-supplied filters (e.g., custom date ranges or model filters) will be vulnerable to SQL injection because parameters are not bound or escaped.
*   **Severity**: High
*   **Recommendation**: Use a proper ORM or a database driver that supports parameterized queries. Avoid executing SQL via shell commands.
