# ══════════════════════════════════════════════════
# FreeRelay — Multi-stage Dockerfile (§19)
# Final image: python:3.12-slim, non-root, <150MB
# ══════════════════════════════════════════════════

# ── Builder ──────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml .
COPY freerelay/ freerelay/
COPY README.md .
COPY dashboard/ dashboard/

RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime ──────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="HrachShah"
LABEL description="FreeRelay — Production AI gateway for free LLM tiers"

# Non-root user
RUN groupadd -r freerelay && useradd -r -g freerelay freerelay

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy app
COPY freerelay/ freerelay/
COPY dashboard/ dashboard/

# Create plugin directory
RUN mkdir -p /home/freerelay/.freerelay/plugins && \
    chown -R freerelay:freerelay /home/freerelay /app

USER freerelay

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=3)" || exit 1

ENTRYPOINT ["python", "-m", "freerelay.cli.main", "start"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
