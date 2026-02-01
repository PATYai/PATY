"""
PATY MCP Server - Control the PATY voice agent via MCP tools.

This server exposes tools for making outbound calls, managing active calls,
and updating participant configuration.
"""

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from livekit import api

# Load environment from root .env.local
load_dotenv("../.env.local")
load_dotenv(".env.local")

# Path to participant.json (at project root)
PARTICIPANT_CONFIG_PATH = Path(
    os.environ.get("PARTICIPANT_CONFIG_PATH", "../participant.json")
)

mcp = FastMCP("PATY Control")


def get_livekit_api() -> api.LiveKitAPI:
    """Create a LiveKit API client."""
    return api.LiveKitAPI()


def load_participant_config() -> dict:
    """Load the current participant configuration."""
    if PARTICIPANT_CONFIG_PATH.exists():
        with open(PARTICIPANT_CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_participant_config(config: dict) -> None:
    """Save the participant configuration."""
    with open(PARTICIPANT_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


@mcp.tool()
async def make_call(
    phone_number: str,
    caller_id: str | None = None,
    room_name: str | None = None,
    participant_name: str | None = None,
) -> dict:
    """
    Initiate an outbound call to the specified phone number.

    Args:
        phone_number: The phone number to call (E.164 format, e.g., +14155551234)
        caller_id: Optional caller ID to display (must be a verified number on your SIP trunk)
        room_name: Optional room name for the call (auto-generated if not provided)
        participant_name: Optional display name for the participant

    Returns:
        A dictionary containing the dispatch details and room information
    """
    lkapi = get_livekit_api()

    try:
        # Load default config for SIP trunk ID and caller ID
        config = load_participant_config()
        sip_trunk_id = config.get("sip_trunk_id") or os.getenv("SIP_OUTBOUND_TRUNK_ID")

        if not sip_trunk_id:
            return {
                "success": False,
                "error": "No SIP trunk ID configured. Set sip_trunk_id in participant.json or SIP_OUTBOUND_TRUNK_ID environment variable.",
            }

        # Generate room name if not provided
        if not room_name:
            room_name = f"paty-call-{uuid.uuid4().hex[:8]}"

        # Use provided caller_id or fall back to config
        effective_caller_id = caller_id or config.get("sip_number")

        # Build metadata for the agent
        metadata = {
            "sip_trunk_id": sip_trunk_id,
            "sip_call_to": phone_number,
            "sip_number": effective_caller_id,
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
            "caller_id": effective_caller_id,
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


@mcp.tool()
async def update_participant_config(
    sip_number: str | None = None,
    sip_trunk_id: str | None = None,
    default_room_name: str | None = None,
) -> dict:
    """
    Update the participant.json configuration.

    Args:
        sip_number: The caller ID phone number to use for outbound calls
        sip_trunk_id: The SIP trunk ID to use for outbound calls
        default_room_name: The default room name for calls

    Returns:
        A dictionary containing the updated configuration
    """
    try:
        config = load_participant_config()

        if sip_number is not None:
            config["sip_number"] = sip_number
        if sip_trunk_id is not None:
            config["sip_trunk_id"] = sip_trunk_id
        if default_room_name is not None:
            config["room_name"] = default_room_name

        save_participant_config(config)

        return {
            "success": True,
            "config": config,
            "message": "Configuration updated successfully",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
async def get_participant_config() -> dict:
    """
    Get the current participant.json configuration.

    Returns:
        A dictionary containing the current configuration
    """
    try:
        config = load_participant_config()
        return {
            "success": True,
            "config": config,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


if __name__ == "__main__":
    # Use PORT env var for Cloud Run compatibility
    port = int(os.environ.get("PORT", 8080))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
