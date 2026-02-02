# outbound/providers/websocket_base.py
"""
WebSocket Connection Coordinator

This module provides a mechanism to coordinate between an HTTP-based API call that initiates
a telephony session and the subsequent incoming WebSocket connection from the telephony provider.
"""
import asyncio
import uuid
import base64
import aiohttp
from typing import Callable, Awaitable
from ..protocol import OutboundProvider, CallRequest, CallSession
from pipecat.transports.base_transport import BaseTransport # This will fail if not mocked, but we will mock it

class WebSocketConnectionCoordinator:
    """
    Correlates outbound API calls with incoming WebSocket connections.
    
    This class acts as a rendezvous point. When a call is initiated, the caller registers
    an expectation for a connection with a specific ID. When the provider connects via
    WebSocket, the connection is matched to the pending expectation.
    """
    
    def __init__(self):
        self._pending: dict[str, asyncio.Future] = {}
    
    def expect_connection(self, call_id: str, timeout: float = 30.0) -> asyncio.Future:
        """
        Register that we're expecting a WebSocket connection for this call.
        
        Args:
            call_id: The unique identifier for the call.
            timeout: How long to wait for the connection before timing out (seconds).
            
        Returns:
            asyncio.Future: A future that will resolve to the WebSocket connection once established.
        """
        future = asyncio.get_event_loop().create_future()
        self._pending[call_id] = future
        
        # Auto-cleanup on timeout
        async def cleanup():
            await asyncio.sleep(timeout)
            if call_id in self._pending and not future.done():
                future.set_exception(TimeoutError(f"No connection for call {call_id}"))
                del self._pending[call_id]
        
        asyncio.create_task(cleanup())
        return future
    
    def connection_received(self, call_id: str, websocket) -> bool:
        """
        Called by webhook handler when WebSocket connection arrives.
        
        Args:
            call_id: The unique identifier for the call.
            websocket: The incoming WebSocket connection object.
            
        Returns:
            bool: True if the connection was expected and successfully handed off, False otherwise.
        """
        if future := self._pending.pop(call_id, None):
            future.set_result(websocket)
            return True
        return False


# outbound/providers/telnyx.py
class TelnyxOutboundProvider(OutboundProvider):
    def __init__(self, config: dict, coordinator: WebSocketConnectionCoordinator):
        self.api_key = config["api_key"]
        self.webhook_base_url = config["webhook_base_url"]
        self.default_caller_id = config.get("caller_id")
        self.coordinator = coordinator
    
    async def initiate_call(self, request: CallRequest) -> CallSession:
        call_id = str(uuid.uuid4())
        
        # Register that we expect a WebSocket connection
        self.coordinator.expect_connection(call_id)
        
        # Initiate via Telnyx Call Control API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.telnyx.com/v2/calls",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "connection_id": self.connection_id,
                    "to": request.to,
                    "from": request.from_ or self.default_caller_id,
                    "webhook_url": f"{self.webhook_base_url}/telnyx/call/{call_id}",
                    "stream_url": f"{self.webhook_base_url.replace('https', 'wss')}/telnyx/ws/{call_id}",
                    "stream_bidirectional_mode": "rtp",
                    "client_state": base64.b64encode(call_id.encode()).decode(),
                }
            ) as resp:
                result = await resp.json()
        
        return CallSession(
            id=call_id,
            provider="telnyx",
            to=request.to,
            from_=request.from_ or self.default_caller_id,
            provider_data={
                "call_control_id": result["data"]["call_control_id"],
            }
        )
    
    async def get_transport(self, session: CallSession) -> BaseTransport:
        # Wait for Telnyx to connect to our WebSocket
        websocket = await self.coordinator.expect_connection(session.id)
        
        transport = FastAPIWebsocketTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                serializer=TelnyxFrameSerializer(),
            )
        )
        return transports