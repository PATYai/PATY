import pytest
import asyncio
from pipecat_outbound.providers.websocket_base import WebSocketConnectionCoordinator

@pytest.mark.asyncio
async def test_coordinator_expect_connection():
    coordinator = WebSocketConnectionCoordinator()
    
    future = coordinator.expect_connection("call-123", timeout=1.0)
    assert not future.done()
    
    # Simulate connection received
    mock_ws = object()
    assert coordinator.connection_received("call-123", mock_ws)
    
    result = await future
    assert result is mock_ws

@pytest.mark.asyncio
async def test_coordinator_timeout():
    coordinator = WebSocketConnectionCoordinator()
    
    future = coordinator.expect_connection("call-timeout", timeout=0.1)
    
    with pytest.raises(TimeoutError, match="No connection for call call-timeout"):
        await future

@pytest.mark.asyncio
async def test_coordinator_unknown_call():
    coordinator = WebSocketConnectionCoordinator()
    assert not coordinator.connection_received("unknown", object())
