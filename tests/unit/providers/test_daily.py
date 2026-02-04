from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipecat_outbound.protocol import CallRequest
from pipecat_outbound.providers.daily import DailyOutboundProvider


@pytest.fixture
def daily_config():
    return {
        "api_key": "fake-key",
        "api_url": "https://api.fake.daily.co/v1"
    }

@pytest.mark.asyncio
async def test_daily_initiate_call(daily_config):
    provider = DailyOutboundProvider(daily_config)

    # Mock aiohttp ClientSession
    mock_room_resp = MagicMock()
    mock_room_resp.json = AsyncMock(return_value={"name": "room1", "url": "https://daily.co/room1"})

    mock_token_resp = MagicMock()
    mock_token_resp.json = AsyncMock(return_value={"token": "fake-token"})

    # We need to mock the context managers for post requests
    mock_session = MagicMock()
    mock_session.post.side_effect = [
        AsyncMock(__aenter__=AsyncMock(return_value=mock_room_resp), __aexit__=AsyncMock()),
        AsyncMock(__aenter__=AsyncMock(return_value=mock_token_resp), __aexit__=AsyncMock())
    ]

    with patch("aiohttp.ClientSession", return_value=mock_session):
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        request = CallRequest(to="+15551234")
        session = await provider.initiate_call(request)

        assert session.id == "room1"
        assert session.provider == "daily"
        assert session.provider_data["room_url"] == "https://daily.co/room1"
        assert session.provider_data["token"] == "fake-token"

@pytest.mark.asyncio
async def test_daily_get_transport(daily_config, mock_dail_transport):
    provider = DailyOutboundProvider(daily_config)

    # Setup a fake session
    class FakeSession:
        id = "room1"
        to = "+15551234"
        provider_data: dict = {"room_url": "url", "token": "token"}  # noqa: RUF012

    transport, start_event = await provider.get_transport(FakeSession())

    assert transport == mock_dail_transport
    assert not start_event.is_set()

    # Verify that we can "call" the handers (just smoke testing the mocking)
    # real logic testing is hard without real transport
