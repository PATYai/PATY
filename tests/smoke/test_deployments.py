"""Smoke tests for Fly.io deployments.

These tests verify that both deployed services are healthy and reachable.
They require the deployed URLs to be accessible and, for authenticated
endpoints, the appropriate API keys.

Environment variables:
    BOT_URL: Bot service URL (default: https://paty-stage-bot.fly.dev)
    MCP_URL: MCP service URL (default: https://paty-stage-mcp.fly.dev)
    MCP_API_KEY: API key for MCP server authentication
    BOT_API_KEY: API key for bot service authentication
"""

import os

import aiohttp
import pytest

BOT_URL = os.environ.get("BOT_URL", "https://paty-stage-bot.fly.dev")
MCP_URL = os.environ.get("MCP_URL", "https://paty-stage-mcp.fly.dev")

MCP_INITIALIZE_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "clientInfo": {"name": "test", "version": "0.1.0"},
        "capabilities": {},
    },
}

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture
def mcp_api_key():
    key = os.environ.get("MCP_API_KEY")
    if not key:
        pytest.skip("MCP_API_KEY not set")
    return key


@pytest.fixture
def bot_api_key():
    key = os.environ.get("BOT_API_KEY")
    if not key:
        pytest.skip("BOT_API_KEY not set")
    return key


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_bot_health():
    """Bot /health endpoint returns 200."""
    async with (
        aiohttp.ClientSession() as session,
        session.get(f"{BOT_URL}/health") as resp,
    ):
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_bot_start_requires_auth(bot_api_key):
    """Bot /start endpoint rejects requests without valid auth."""
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{BOT_URL}/start",
            json={"room_url": "x", "token": "x", "phone_number": "x"},
        ) as resp,
    ):
        assert resp.status == 401


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_mcp_reachable():
    """MCP server responds on its base URL (expects 405 for GET on POST-only endpoint)."""
    async with (
        aiohttp.ClientSession() as session,
        session.get(f"{MCP_URL}/mcp") as resp,
    ):
        # Streamable HTTP MCP only accepts POST; GET should not 502/503
        assert resp.status != 502
        assert resp.status != 503


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_mcp_post_requires_auth(mcp_api_key):
    """MCP server rejects unauthenticated POST requests."""
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{MCP_URL}/mcp",
            headers=MCP_HEADERS,
            json=MCP_INITIALIZE_BODY,
        ) as resp,
    ):
        assert resp.status in (401, 403)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_mcp_authenticated_initialize(mcp_api_key):
    """MCP server accepts authenticated initialize request."""
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {mcp_api_key}"}
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{MCP_URL}/mcp",
            headers=headers,
            json=MCP_INITIALIZE_BODY,
        ) as resp,
    ):
        assert resp.status == 200
        data = await resp.json()
        assert (
            data.get("result", {}).get("serverInfo", {}).get("name") == "PATY Control"
        )
