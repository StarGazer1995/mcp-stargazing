# mcp-stargazing

Calculate the altitude, rise, and set times of celestial objects (Sun, Moon, planets, stars, and deep-space objects) for any location on Earth, with optional light pollution analysis.

## Features

- **Altitude/Azimuth Calculation**: Get elevation and compass direction for any celestial object.
- **Rise/Set Times**: Determine when objects appear/disappear above the horizon.
- **Light Pollution Analysis**: Load and analyze light pollution maps (GeoTIFF format).
- **Code Execution Ready**:
  - **Serializable Returns**: All tools return JSON-serializable data (ISO strings for dates), making them directly usable by LLMs.
  - **Pagination**: `analysis_area` supports paging (`page`, `page_size`) to handle large datasets efficiently.
  - **Standardized Responses**: Uniform response format `{ "data": ..., "_meta": ... }` for better observability and error handling.
- **Performance**:
  - **Async Execution**: Non-blocking celestial calculations.
  - **Caching**: Intelligent caching for Simbad queries and regional analysis.
  - **Proxy Support**: Native support for HTTP/HTTPS proxies (useful for downloading astronomical data).
- **Time Zone Aware**: Works with local or UTC times.

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

1. **Install `uv`**:
   ```bash
   pip install uv
   ```

2. **Sync dependencies**:
   ```bash
   uv sync
   ```
   This will create a virtual environment in `.venv` and install all dependencies defined in `pyproject.toml`.

3. **Activate the environment**:
   ```bash
   source .venv/bin/activate
   ```

## MCP Server Usage

Start the MCP server to expose tools to AI agents or other clients.

### 1. Environment Setup

Create a `.env` file or export variables:

```bash
# Required for weather tools
export QWEATHER_API_KEY="your_api_key"

# Optional: Proxy for downloading astronomical data (Simbad/IERS)
# Highly recommended if you are in a restricted network environment
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
```

### 2. Start Server

**Streamable HTTP (SHTTP) mode** (Recommended for most agents):

```bash
# Basic start
python -m src.main --mode shttp --port 3001 --path /shttp

# With proxy explicitly passed (overrides env vars)
python -m src.main --mode shttp --port 3001 --path /shttp --proxy http://127.0.0.1:7890
```

**SSE mode**:

```bash
python -m src.main --mode sse --port 3001 --path /sse
```

### 3. Response Format

All tools return data in a standardized JSON format:

```json
{
  "data": {
    // Tool-specific return data
    "altitude": 45.5,
    "azimuth": 180.0
  },
  "_meta": {
    "version": "1.0.0",
    "status": "success"
  }
}
```

### 4. Available Tools

- **`get_celestial_pos`**: Calculate altitude/azimuth.
- **`get_celestial_rise_set`**: Calculate rise/set times (Returns ISO strings).
- **`get_weather_by_name` / `get_weather_by_position`**: Fetch current weather.
- **`get_local_datetime_info`**: Get current local time information.
- **`analysis_area`**: Find best stargazing spots in a region.
  - **Inputs**: `top_left`, `bottom_right`, `time`, `page`, `page_size`.
  - **Returns**: List of spots with viewing conditions, plus pagination metadata (`total`, `resource_id`).

## Examples

- **Orchestration**: `python examples/code_execution_orchestration.py`
  - Demonstrates a full workflow: Get time -> Get Celestial Pos -> Check Weather -> Find Spots.
  - Shows how to handle the standardized response format programmatically.

- **Pagination**: `python examples/pagination_demo.py`
  - Demonstrates fetching large result sets page by page using the `resource_id`.

## Project Structure

The project is modularized for better maintainability and code execution support:

```
.
├── src/
│   ├── functions/            # Tool implementations grouped by domain
│   │   ├── celestial/        # Celestial calculations (pos, rise/set)
│   │   ├── weather/          # Weather API integration
│   │   ├── places/           # Location and area analysis
│   │   └── time/             # Time utilities
│   ├── cache.py              # Caching logic for analysis results
│   ├── response.py           # Standardized response formatting
│   ├── server_instance.py    # FastMCP server instance (avoids circular imports)
│   ├── main.py               # Entry point and tool registration
│   ├── celestial.py          # Core astronomy logic (Astropy wrappers)
│   ├── placefinder.py        # Grid analysis logic
│   └── qweather_interaction.py # Weather API client
├── tests/                    # Unified test suite
│   ├── test_celestial.py
│   ├── test_weather.py
│   ├── test_serialization.py # Validates JSON return formats
│   └── test_integration.py   # End-to-end flow tests
├── examples/                 # Usage examples
├── docs/                     # Documentation and improvement plans
└── pyproject.toml            # Project configuration and dependencies
```

## Testing

Run the unified test suite:

```bash
pytest tests/
```

Key tests include:
- `test_serialization.py`: Ensures all tools return valid JSON with the correct schema.
- `test_integration.py`: Mocks external APIs to verify the entire toolchain.

## Contributing

1.  Follow the [Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) best practices.
2.  Ensure all new tools return standard JSON responses using `src.response.format_response`.
3.  Add tests in `tests/` for any new functionality.
