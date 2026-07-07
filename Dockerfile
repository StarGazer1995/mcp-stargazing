FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

WORKDIR /app

# Install system dependencies required by rasterio (GDAL)
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends libexpat1 git supervisor && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    ASTROPY_IERS_AUTO_DOWNLOAD=0 \
    STARGAZING_DB_CONFIG="/app/config.example.toml" \
    PATH="/app/.venv/bin:$PATH"

# Install system dependencies required by rasterio native extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# --- Shared data stage (runs download once, reused by test & production) ---
FROM base AS data

RUN python -m pip install --no-cache-dir setuptools wheel && \
    uv sync --frozen --no-install-project --no-dev && \
    uv cache clean

COPY scripts/download_data.py ./scripts/
RUN uv run python scripts/download_data.py

# --- Test Stage ---
FROM base AS test

# Install dependencies including dev dependencies.
RUN python -m pip install --no-cache-dir setuptools wheel && \
    uv sync --frozen --no-install-project && \
    uv cache clean

# Copy application code
COPY . .

# Install project including dev dependencies
RUN uv sync --frozen && \
    uv cache clean

# Copy pre-downloaded catalog data from shared stage
COPY --from=data /app/src/data/ ./src/data/

# Run tests from the synced virtual environment.
ENTRYPOINT ["pytest"]
CMD ["-v"]

# --- Production Stage ---
FROM base AS production

# Install dependencies and clean cache to minimize image size
RUN python -m pip install --no-cache-dir setuptools wheel && \
    uv sync --frozen --no-install-project --no-dev && \
    uv cache clean

# Copy application code
COPY . .

# Install project and clean cache
RUN uv sync --frozen --no-dev && \
    uv cache clean

# Copy pre-downloaded catalog data from shared stage
COPY --from=data /app/src/data/ ./src/data/

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports (MCP + SPF web)
EXPOSE 3001 5001

# Run both services via supervisord
ENTRYPOINT ["supervisord"]
CMD ["-c", "/etc/supervisor/conf.d/supervisord.conf"]
