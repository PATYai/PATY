# Testing pipecat_outbound

This directory contains the test suite for `pipecat_outbound`.

## Structure

- `unit/`: Unit tests that mock all external dependencies. Fast and safe to run anywhere.
- `smoke/`: Integration tests that hit real external APIs (Daily, etc.). These require API keys.

## Running Tests

### Prerequisites

Install `uv` if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install dependencies:
```bash
uv sync --all-extras
```

### Running Unit Tests

Run all unit tests:
```bash
uv run pytest tests/unit
```

### Linting

Run linting:
```bash
uv run ruff check .
```

### Running Smoke Tests

Smoke tests are marked with `@pytest.mark.smoke`. They are skipped if the required environment variables are not set.

To run smoke tests, export your API keys:
```bash
export DAILY_API_KEY="your_api_key"
uv run pytest tests/smoke
```

Or run everything:
```bash
uv run pytest tests/
```

## Adding New Tests

- Use `pytest-asyncio` for async tests.
- Place unit tests in `tests/unit`.
- Place integration/smoke tests in `tests/smoke` and guard them with environment variable checks.
