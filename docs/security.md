# Security

FreeRelay v3 MAX treats security as a control-plane responsibility with data-plane enforcement. This document captures the baseline threat model and mitigations.

## Threat Model

- Secret leakage (provider keys, tenant tokens).
- Prompt injection and tool misuse.
- Data exfiltration through tools or retrieval.
- PII exposure in logs, caches, or traces.
- Replay/reuse of requests across tenants.

## Controls

### Tenant Isolation

- Per-tenant secrets isolation.
- Namespace-scoped rate limits and budgets.
- Policy DSL enforces allowed providers and tool scopes.

### Encryption & Key Management

- KMS-backed encryption for stored secrets.
- AES-256-GCM for local encryption at rest.
- HMAC signing for audit trails.

### PII Detection & Redaction

- Regex + NER checks for email, phone, SSN, and address patterns.
- Configurable redaction policies in the context pipeline.
- Sanitized logs and traces; no raw prompt storage in observability.

### Prompt Injection & Jailbreak Defense

- Input filtering to detect jailbreak patterns.
- Tool-guardrail enforcement with allow/deny lists.
- Safety posture gates via tenant policy.

### Tool Provenance & Safety

- Tool output labels and provenance metadata.
- Trust tiers for retrieval documents and tool responses.
- Optional human approval gates for high-risk tool use.

### Audit & Forensics

- Signed audit records in `freerelay:outcomes` and tenant audit streams.
- Immutable routing decision history.
- Replayability with frozen prompts and tool outputs.

## Data Retention

- Configurable retention windows for caches, outcome streams, and agent state.
- Default outcomes retention: 7 days.
- Default idempotency retention: 300 seconds.

## Operational Hardening

- Non-root Docker runtime.
- Health checks and circuit-breaker isolation.
- Brownout mode to preserve safety-critical paths.
- Least-privilege egress rules for tools.

## Security Checklist

- Secrets loaded only via env or encrypted store.
- No plaintext secrets in configs or Dockerfiles.
- Logs and traces scrub sensitive payloads.
- Tenant policy requires explicit permission for tools.
