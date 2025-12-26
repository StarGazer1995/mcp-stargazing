FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

WORKDIR /app

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    QWEATHER_API_KEY="" \
    STARGAZING_DB_CONFIG="/app/config.example.toml"

# Copy dependency files
COPY pyproject.toml uv.lock ./

# --- Test Stage ---
FROM base AS test

# Install dependencies including dev dependencies
RUN uv sync --frozen --no-install-project && \
    uv cache clean

# Copy application code
COPY . .

# Install project including dev dependencies
RUN uv sync --frozen && \
    uv cache clean

# Initialize data (download astronomical catalogs)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

RUN uv run python scripts/download_data.py

# Run tests
ENTRYPOINT ["uv", "run", "pytest"]
CMD ["tests/", "-v"]

# --- Production Stage ---
FROM base AS production

# Install dependencies and clean cache to minimize image size
# We run sync and cache clean in the same layer
RUN uv sync --frozen --no-install-project --no-dev && \
    uv cache clean

# Copy application code
COPY . .

# Install project and clean cache
RUN uv sync --frozen --no-dev && \
    uv cache clean

# Initialize data (download astronomical catalogs)
# This step requires internet access.
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

RUN uv run python scripts/download_data.py

# Expose port
EXPOSE 3001

# Run the application using uv run to ensure environment is set up
ENTRYPOINT ["uv", "run", "mcp-stargazing"]
CMD ["--mode", "shttp", "--port", "3001", "--path", "/shttp"]
