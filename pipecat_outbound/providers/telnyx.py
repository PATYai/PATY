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
