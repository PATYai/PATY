# outbound/protocol.py
"""
Outbound Protocol Definitions

This module defines the core protocols, dataclasses, and interfaces used
by the outbound calling system. It establishes the contract between the
caller logic and various provider implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pipecat.transports.base_transport import BaseTransport


@dataclass
class CallRequest:
    """
    Encapsulates the parameters for initiating an outbound call.

    Attributes:
        to: The destination identifier (phone number, SIP URI, etc.).
        from_: Optional source identifier (caller ID).
        metadata: Optional dictionary of additional data to pass to the provider.
    """

    to: str
    from_: str | None = None
    metadata: dict | None = None


@dataclass
class CallSession:
    """
    Represents an initiated outbound call session.

    Attributes:
        id: Unique identifier for the call (provider-specific).
        provider: Name of the provider handling the call.
        to: The destination identifier.
        from_: The source identifier.
        status: Current status of the call (e.g., "initiated", "connected").
        provider_data: Optional dictionary containing provider-specific session details.
    """

    id: str
    provider: str
    to: str
    from_: str
    status: str = "initiated"
    provider_data: dict | None = None


class OutboundProvider(ABC):
    """
    Abstract Base Class for all outbound telephony providers.

    Any new provider (e.g., Twilio, Telnyx) must implement this interface
    to be compatible with the OutboundCaller.
    """

    @abstractmethod
    async def initiate_call(self, request: CallRequest) -> CallSession:
        """
        Start the outbound call.

        This method should initiate the call with the provider API and return
        immediately with session information.

        Args:
            request: The CallRequest object containing call details.

        Returns:
            CallSession: A session object identifying the new call.
        """
        ...

    @abstractmethod
    async def get_transport(self, session: CallSession) -> BaseTransport:
        """
        Get a connected transport for this call session.

        This method typically waits for the media connection to be established or
        prepares the transport for immediate use.

        Args:
            session: The active CallSession.

        Returns:
            BaseTransport: An initialized Pipecat transport ready for processing audio.
        """
        ...

    @abstractmethod
    async def hangup(self, session: CallSession) -> None:
        """
        Terminate the call.

        Args:
            session: The active CallSession to terminate.
        """
        ...
