import sys
from unittest.mock import MagicMock

import pytest

# Mock pipecat modules BEFORE they are imported by any code
mock_pipecat = MagicMock()
sys.modules["pipecat"] = mock_pipecat

mock_base_transport = MagicMock()
sys.modules["pipecat.transports"] = MagicMock()
sys.modules["pipecat.transports.base_transport"] = mock_base_transport
mock_base_transport.BaseTransport = MagicMock

mock_daily = MagicMock()
sys.modules["pipecat.transports.services"] = MagicMock()
sys.modules["pipecat.transports.services.daily"] = mock_daily
mock_daily.DailyTransport = MagicMock
mock_daily.DailyParams = MagicMock

mock_vad = MagicMock()
sys.modules["pipecat.audio"] = MagicMock()
sys.modules["pipecat.audio.vad"] = MagicMock()
sys.modules["pipecat.audio.vad.silero"] = mock_vad
mock_vad.SileroVADAnalyzer = MagicMock

@pytest.fixture
def mock_aioresponse():
    # Only if we use aioresponses, otherwise mock aiohttp session manually
    pass

@pytest.fixture
def sample_config():
    return {
        "providers": {
            "daily": {
                "type": "daily",
                "api_key": "test_key",
                "api_url": "https://api.daily.co/v1"
            },
            "telnyx": {
                "type": "telnyx",
                "api_key": "test_key",
                "webhook_base_url": "https://example.com"
            }
        },
        "routing": {
            "rules": [
                {"pattern": "^\\+1", "provider": "daily"},
                {"pattern": "^\\+44", "provider": "telnyx"}
            ],
            "default": "daily"
        }
    }

@pytest.fixture
def mock_params():
    return MagicMock()

@pytest.fixture
def mock_dail_transport(monkeypatch):
    """Mock DailyTransport to avoid imports or real initialization"""
    mock_transport = MagicMock()
    # Ensure event_handler is a decorator that returns the function
    mock_transport.event_handler = MagicMock(side_effect=lambda x: lambda f: f)

    # Mock the class
    mock_cls = MagicMock(return_value=mock_transport)
    monkeypatch.setattr("pipecat_outbound.providers.daily.DailyTransport", mock_cls)

    return mock_transport
