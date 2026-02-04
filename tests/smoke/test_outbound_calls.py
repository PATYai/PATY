import os

import pytest

from pipecat_outbound.protocol import CallRequest
from pipecat_outbound.providers.daily import DailyOutboundProvider

# pytestmark = pytest.mark.smoke
# Note: we need to register the marker in pytest.ini or pyproject.toml to avoid warnings,
# or just use it.

@pytest.fixture
def daily_api_key():
    key = os.environ.get("DAILY_API_KEY")
    if not key:
        pytest.skip("DAILY_API_KEY not set")
    return key

@pytest.mark.smoke
@pytest.mark.asyncio
async def test_daily_dialout_real_api(daily_api_key):
    """
    Smoke test that actually hits the Daily API to create a room and token.
    It does NOT verify the actual SIP dialout connects (that requires a real phone),
    but it verifies the API integration works.
    """
    config = {
        "api_key": daily_api_key,
        "api_url": "https://api.daily.co/v1"
    }

    provider = DailyOutboundProvider(config)

    # We use a dummy number. expected behavior: room created, token created, session returned.
    # The VAD/transport part would fail if we tried to connect, but initiate_call should work.
    req = CallRequest(to="+15550000000")

    try:
        session = await provider.initiate_call(req)

        assert session.provider == "daily"
        assert session.id  # Should be the room name
        assert session.provider_data.get("room_url")
        assert session.provider_data.get("token")

        print(f"Successfully created Daily room: {session.provider_data['room_url']}")

    except Exception as e:
        pytest.fail(f"Daily API call failed: {e}")
