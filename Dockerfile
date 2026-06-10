FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

WORKDIR /app

# Install system dependencies required by rasterio (GDAL)
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends libexpat1 && \
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

# --- Test Stage ---
FROM base AS test

# Install dependencies including dev dependencies.
# Docker's predefined proxy build args are available to RUN steps without
# being declared in the Dockerfile, so they do not persist in image metadata.
RUN python -m pip install --no-cache-dir setuptools wheel && \
    uv sync --frozen --no-install-project && \
    uv cache clean

# Copy application code
COPY . .

# Install project including dev dependencies
RUN uv sync --frozen && \
    uv cache clean

# Initialize data (download astronomical catalogs)
RUN uv run python scripts/download_data.py

# Run tests from the synced virtual environment.
ENTRYPOINT ["pytest"]
CMD ["tests/", "-v"]

# --- Production Stage ---
FROM base AS production

# Install dependencies and clean cache to minimize image size
# We run sync and cache clean in the same layer
RUN python -m pip install --no-cache-dir setuptools wheel && \
    uv sync --frozen --no-install-project --no-dev && \
    uv cache clean

# Copy application code
COPY . .

# Install project and clean cache
RUN uv sync --frozen --no-dev && \
    uv cache clean

# Initialize data (download astronomical catalogs)
# This step requires internet access.
RUN uv run python scripts/download_data.py

# Expose port
EXPOSE 3001

# Run the application from the synced virtual environment to avoid
# re-building the project at container startup.
ENTRYPOINT ["mcp-stargazing"]
CMD ["--mode", "shttp", "--port", "3001", "--path", "/shttp"]
