"""Smoke tests for the web frontend.

Environment variables:
    WEB_URL: Web frontend URL (default: https://paty-web.fly.dev)
"""

import os

import aiohttp
import pytest

WEB_URL = os.environ.get("WEB_URL", "https://paty-web.fly.dev")


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_web_landing_page():
    """Landing page returns 200 with expected content."""
    async with (
        aiohttp.ClientSession() as session,
        session.get(WEB_URL) as resp,
    ):
        assert resp.status == 200
        text = await resp.text()
        assert "PATY" in text


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_web_dashboard_redirects_unauthenticated():
    """Dashboard redirects unauthenticated users to sign-in."""
    async with (
        aiohttp.ClientSession() as session,
        session.get(f"{WEB_URL}/dashboard", allow_redirects=False) as resp,
    ):
        # Expect a redirect (3xx) to sign-in
        assert resp.status in range(300, 400)
        location = resp.headers.get("location", "")
        assert "sign-in" in location
