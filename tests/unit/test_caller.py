import os
import pytest
import yaml
from unittest.mock import patch, mock_open
from pipecat_outbound.caller import OutboundCaller

@pytest.fixture
def mock_config_yaml():
    return """
providers:
  daily:
    type: daily
    api_key: ${DAILY_API_KEY}
    api_url: ${DAILY_API_URL}
routing:
  rules:
    - pattern: "^\\\\+1"
      provider: daily
  default: daily
"""

def test_expand_env_vars(monkeypatch):
    caller = OutboundCaller.__new__(OutboundCaller) # Bypass init
    
    monkeypatch.setenv("TEST_VAR", "expanded")
    
    # Test string
    assert caller._expand_env_vars("val-${TEST_VAR}") == "val-expanded"
    assert caller._expand_env_vars("val-${MISSING}") == "val-${MISSING}"
    
    # Test dict
    assert caller._expand_env_vars({"k": "${TEST_VAR}"}) == {"k": "expanded"}
    
    # Test list
    assert caller._expand_env_vars(["${TEST_VAR}"]) == ["expanded"]

def test_load_config_mocks(mock_config_yaml, monkeypatch):
    monkeypatch.setenv("DAILY_API_KEY", "secret-key")
    monkeypatch.setenv("DAILY_API_URL", "https://daily.co")
    
    with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
        caller = OutboundCaller("fake_path.yaml")
        
        assert caller.config["providers"]["daily"]["api_key"] == "secret-key"
        assert caller.config["providers"]["daily"]["api_url"] == "https://daily.co"

def test_select_provider(mock_config_yaml, monkeypatch):
    # Setup mock config directly
    config = yaml.safe_load(mock_config_yaml)
    caller = OutboundCaller.__new__(OutboundCaller)
    caller.config = config
    
    # Create mock providers
    start_caller_providers = {
        "daily": "daily_provider",
    }
    caller.providers = start_caller_providers
    
    # Default behavior
    assert caller._select_provider("+44123456") == "daily_provider"
    
    # Regex match
    assert caller._select_provider("+15551234") == "daily_provider"
