# outbound/providers/websocket_base.py
"""
WebSocket Connection Coordinator

This module provides a mechanism to coordinate between an HTTP-based API call that initiates
a telephony session and the subsequent incoming WebSocket connection from the telephony provider.
"""

import asyncio


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

        self._cleanup_task = asyncio.create_task(cleanup())
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
