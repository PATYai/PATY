# outbound/providers/telnyx.py
"""
Telnyx Outbound Provider

This module implements the OutboundProvider interface for Telnyx.
It uses Telnyx's Call Control API to initiate calls and establishes media streaming
via WebSocket.
"""

import base64
import uuid

import aiohttp
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from ..protocol import CallRequest, CallSession, OutboundProvider
from .websocket_base import WebSocketConnectionCoordinator


class TelnyxOutboundProvider(OutboundProvider):
    """
    Provider implementation for Telnyx.

    Initiates outbound calls using the Telnyx V2 Call Control API and handles
    bidirectional audio streaming over WebSocket.
    """

    def __init__(self, config: dict, coordinator: WebSocketConnectionCoordinator):
        """
        Initialize the Telnyx provider.

        Args:
            config: Configuration containing 'api_key', 'webhook_base_url', and optional 'caller_id'.
            coordinator: Shared WebSocket coordinator to match API calls with incoming socket connections.
        """
        self.api_key = config["api_key"]
        self.webhook_base_url = config["webhook_base_url"]
        self.default_caller_id = config.get("caller_id")
        self.coordinator = coordinator

    async def initiate_call(self, request: CallRequest) -> CallSession:
        """
        Initiate a call via Telnyx Call Control API.

        Args:
            request: The call request details.

        Returns:
            CallSession: Session containing the call control ID.
        """
        call_id = str(uuid.uuid4())

        # Register that we expect a WebSocket connection
        self.coordinator.expect_connection(call_id)

        # Initiate via Telnyx Call Control API
        async with (
            aiohttp.ClientSession() as http_session,
            http_session.post(
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
                },
            ) as resp,
        ):
            result = await resp.json()

        return CallSession(
            id=call_id,
            provider="telnyx",
            to=request.to,
            from_=request.from_ or self.default_caller_id,
            provider_data={
                "call_control_id": result["data"]["call_control_id"],
            },
        )

    async def get_transport(self, session: CallSession) -> BaseTransport:
        """
        Wait for and retrieve the WebSocket transport for the call.

        Args:
            session: The active call session.

        Returns:
            BaseTransport: The connected FastAPIWebsocketTransport.
        """
        # Wait for Telnyx to connect to our WebSocket
        websocket = await self.coordinator.expect_connection(session.id)

        transport = FastAPIWebsocketTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                serializer=TelnyxFrameSerializer(),
            ),
        )
        return transport

    async def hangup(self, session: CallSession) -> None:
        """
        Terminate the Telnyx call.

        Args:
            session: The session to terminate.
        """
        # Implementation dependent on how we want to hang up (e.g. API call)
        # Leaving as placeholder since original code didn't implement it
        pass
