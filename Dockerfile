# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    QWEATHER_API_KEY="" \
    STARGAZING_DB_CONFIG="/app/config.example.toml"

# Set working directory
WORKDIR /app

# Copy dependency files first to leverage cache
COPY pyproject.toml uv.lock ./

# Install dependencies 
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application
COPY . .

# Copy config example to root for easy reference
COPY examples/postgis_config.toml /app/config.example.toml

# Install the project
RUN uv sync --frozen --no-dev

# Initialize data (download astronomical catalogs)
# This step requires internet access. 
# If you are behind a proxy, build with: docker build --build-arg HTTP_PROXY=... .
RUN uv run python scripts/download_data.py

# Expose port
EXPOSE 3001

# Run the application
# Default to SHTTP mode
ENTRYPOINT ["uv", "run", "mcp-stargazing"]
CMD ["--mode", "shttp", "--port", "3001", "--path", "/shttp"]
