"""
PATY MCP Server - Control the PATY voice agent via MCP tools.

This server exposes tools for making outbound calls and managing active calls.

Authentication:
    Set MCP_API_KEY environment variable to require Bearer token authentication.
    If not set, the server runs without authentication (not recommended for production).
"""

import json
import os
import uuid

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from livekit import api


class ApiKeyVerifier(TokenVerifier):
    """Simple API key verifier that validates against an environment variable."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def verify_token(self, token: str) -> AccessToken | None:
        if token == self.api_key:
            return AccessToken(
                token=token,
                client_id="api-key-client",
                scopes=["all"],
            )
        return None


# Load environment from root .env.local
load_dotenv("../.env.local")
load_dotenv(".env.local")

# Configure authentication (required by default)
# Set MCP_AUTH_DISABLED=true to explicitly disable auth (e.g., for Cloud Run with IAM)
auth_disabled = os.environ.get("MCP_AUTH_DISABLED", "").lower() == "true"
api_key = os.environ.get("MCP_API_KEY")

if auth_disabled:
    auth_provider = None
elif api_key:
    auth_provider = ApiKeyVerifier(api_key)
else:
    raise RuntimeError(
        "MCP_API_KEY must be set for authentication. "
        "Set MCP_AUTH_DISABLED=true to explicitly disable auth."
    )

mcp = FastMCP("PATY Control", auth=auth_provider)


def get_livekit_api() -> api.LiveKitAPI:
    """Create a LiveKit API client."""
    return api.LiveKitAPI()


@mcp.tool()
async def make_call(
    phone_number: str,
    sip_trunk_id: str | None = None,
    caller_id: str | None = None,
    room_name: str | None = None,
    participant_name: str | None = None,
) -> dict:
    """
    Initiate an outbound call to the specified phone number.

    Args:
        phone_number: The phone number to call (E.164 format, e.g., +14155551234)
        sip_trunk_id: The SIP trunk ID to use (falls back to SIP_OUTBOUND_TRUNK_ID env var)
        caller_id: The caller ID to display (must be a verified number on your SIP trunk)
        room_name: Optional room name for the call (auto-generated if not provided)
        participant_name: Optional display name for the participant

    Returns:
        A dictionary containing the dispatch details and room information
    """
    lkapi = get_livekit_api()

    try:
        # Use provided trunk ID or fall back to environment variable
        effective_trunk_id = sip_trunk_id or os.getenv("SIP_OUTBOUND_TRUNK_ID")

        if not effective_trunk_id:
            return {
                "success": False,
                "error": "No SIP trunk ID provided. Pass sip_trunk_id or set SIP_OUTBOUND_TRUNK_ID environment variable.",
            }

        # Generate room name if not provided
        if not room_name:
            room_name = f"paty-call-{uuid.uuid4().hex[:8]}"

        # Build metadata for the agent
        metadata = {
            "sip_trunk_id": effective_trunk_id,
            "sip_call_to": phone_number,
            "sip_number": caller_id,
            "room_name": room_name,
            "participant_identity": phone_number,
            "participant_name": participant_name or "",
        }

        # Dispatch the voice agent to handle the call
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="paty-voice",
                room=room_name,
                metadata=json.dumps(metadata),
            )
        )

        return {
            "success": True,
            "room_name": room_name,
            "phone_number": phone_number,
            "caller_id": caller_id,
            "dispatch_id": dispatch.dispatch_id,
            "message": f"Call initiated to {phone_number}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        await lkapi.aclose()


@mcp.tool()
async def end_call(room_name: str) -> dict:
    """
    End an active call by deleting the room.

    Args:
        room_name: The name of the room/call to end

    Returns:
        A dictionary indicating success or failure
    """
    lkapi = get_livekit_api()

    try:
        await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
        return {
            "success": True,
            "message": f"Call in room '{room_name}' has been ended",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        await lkapi.aclose()


@mcp.tool()
async def list_rooms() -> dict:
    """
    List all active rooms/calls.

    Returns:
        A dictionary containing the list of active rooms with their details
    """
    lkapi = get_livekit_api()

    try:
        response = await lkapi.room.list_rooms(api.ListRoomsRequest())
        rooms = []
        for room in response.rooms:
            rooms.append(
                {
                    "name": room.name,
                    "sid": room.sid,
                    "num_participants": room.num_participants,
                    "creation_time": room.creation_time,
                    "metadata": room.metadata,
                }
            )
        return {
            "success": True,
            "rooms": rooms,
            "count": len(rooms),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        await lkapi.aclose()


@mcp.tool()
async def get_call_status(room_name: str) -> dict:
    """
    Get the status of a specific call/room.

    Args:
        room_name: The name of the room to check

    Returns:
        A dictionary containing the room status and participant information
    """
    lkapi = get_livekit_api()

    try:
        # List rooms and find the matching one
        response = await lkapi.room.list_rooms(api.ListRoomsRequest(names=[room_name]))

        if not response.rooms:
            return {
                "success": False,
                "error": f"Room '{room_name}' not found",
            }

        room = response.rooms[0]

        # Get participants in the room
        participants_response = await lkapi.room.list_participants(
            api.ListParticipantsRequest(room=room_name)
        )

        participants = []
        for p in participants_response.participants:
            participants.append(
                {
                    "identity": p.identity,
                    "name": p.name,
                    "state": str(p.state),
                    "joined_at": p.joined_at,
                    "metadata": p.metadata,
                }
            )

        return {
            "success": True,
            "room": {
                "name": room.name,
                "sid": room.sid,
                "num_participants": room.num_participants,
                "creation_time": room.creation_time,
                "metadata": room.metadata,
            },
            "participants": participants,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        await lkapi.aclose()


if __name__ == "__main__":
    # Use PORT env var for Cloud Run compatibility
    port = int(os.environ.get("PORT", 8080))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
