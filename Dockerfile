# ─── Stage 1: Builder ─────────────────────────────────────────────────────────
# Pinned to a specific patch version + digest, not the floating `3.12-slim`
# tag — rebuilds on different days previously could silently pull different
# underlying images. To bump: `docker pull python:3.12-slim`, take the new
# digest from the pull output, update both FROM lines below (build stage and
# runtime stage — they must match), and confirm `docker build .` still works.
FROM python:3.12.13-slim@sha256:64695412729fbe8cf054511723820c82bbe5a077d4a6b4070cd4a7225d3422ce AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install uv for faster dependency resolution.
RUN pip install uv

COPY pyproject.toml README.md ./
# Install deps into an isolated prefix so we can copy only what's needed.
RUN uv pip install --system .


# ─── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12.13-slim@sha256:64695412729fbe8cf054511723820c82bbe5a077d4a6b4070cd4a7225d3422ce AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Create non-root user.
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copy installed packages from builder stage.
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source (no tests in runtime image).
COPY app ./app

# Own the workdir.
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "app.main"]
