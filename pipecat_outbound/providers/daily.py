# outbound/providers/daily.py
"""
Daily.co Outbound Provider

This module implements the OutboundProvider interface for Daily.co.
It manages room creation, token generation, and the SIP dial-out process
via Daily's transport services.
"""
import aiohttp
import time
import asyncio
from ..protocol import OutboundProvider, CallRequest, CallSession
from pipecat.transports.services.daily import DailyTransport, DailyParams
from pipecat.audio.vad.silero import SileroVADAnalyzer

class OutboundCallError(Exception):
    """Raised when an outbound call fails to initiate or connect."""
    pass

class DailyOutboundProvider(OutboundProvider):
    """
    Provider implementation for Daily.co SIP dial-out.
    
    Uses Daily's REST API to create a room and initiate a SIP call to the destination.
    """
    
    def __init__(self, config: dict):
        """
        Initialize the Daily provider.
        
        Args:
            config: Configuration dictionary containing 'api_key', 'api_url', and optional 'caller_id'.
        """
        self.api_key = config["api_key"]
        self.api_url = config.get("api_url", "https://api.daily.co/v1")
        self.default_caller_id = config.get("caller_id")
        self._transports: dict[str, DailyTransport] = {}
    
    async def initiate_call(self, request: CallRequest) -> CallSession:
        """
        Create a Daily room and configure it for dial-out.
        
        Args:
            request: The call request details.
            
        Returns:
            CallSession: Session containing the room URL and token.
        """
        # Create a Daily room with SIP enabled
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/rooms",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "properties": {
                        "enable_dialout": True,
                        "sip": {"sip_mode": "dial-out"},
                        "exp": int(time.time()) + 3600,
                    }
                }
            ) as resp:
                room = await resp.json()
        
            # Get a token
            async with session.post(
                f"{self.api_url}/meeting-tokens",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"properties": {"room_name": room["name"], "is_owner": True}}
            ) as resp:
                token_data = await resp.json()
        
        return CallSession(
            id=room["name"],
            provider="daily",
            to=request.to,
            from_=request.from_ or self.default_caller_id,
            provider_data={
                "room_url": room["url"],
                "token": token_data["token"],
            }
        )
    
    async def get_transport(self, session: CallSession) -> DailyTransport:
        """
        Initialize and connect the DailyTransport.
        
        This method joins the bot to the Daily room and triggers the actual SIP dial-out
        to the destination number once joined.
        
        Args:
            session: The active call session.
            
        Returns:
            DailyTransport: The connected transport instance.
        """
        transport = DailyTransport(
            session.provider_data["room_url"],
            session.provider_data["token"],
            "OutboundBot",
            DailyParams(
                api_key=self.api_key,
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            )
        )
        
        # Store for later hangup
        self._transports[session.id] = transport
        
        # The actual dial-out happens after transport joins
        # We register a handler to initiate once ready
        call_started = asyncio.Event()
        
        @transport.event_handler("on_joined")
        async def on_joined(t, data):
            await transport.start_dialout(session.to)
        
        @transport.event_handler("on_dialout_connected")
        async def on_connected(t, data):
            call_started.set()
        
        @transport.event_handler("on_dialout_error")
        async def on_error(t, data):
            raise OutboundCallError(f"Dial-out failed: {data}")
        
        return transport, call_started
    
    async def hangup(self, session: CallSession) -> None:
        """
        Stop the dial-out and leave the room.
        
        Args:
            session: The session to terminate.
        """
        if transport := self._transports.get(session.id):
            await transport.stop_dialout()