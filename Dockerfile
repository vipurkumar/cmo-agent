FROM python:3.12-slim

# Security: run as non-root user
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --create-home app

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Build frontend (multi-stage would be cleaner but keeping it simple)
COPY frontend/ frontend/
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && \
    cd frontend && npm ci && npm run build && \
    rm -rf node_modules && \
    apt-get purge -y nodejs npm && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY src/ src/
COPY knowledge/ knowledge/
COPY infra/ infra/

# Set ownership
RUN chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
