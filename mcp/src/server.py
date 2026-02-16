"""
PATY MCP Server - Control the PATY voice agent via MCP tools.

This server exposes tools for making outbound calls using Daily and Pipecat.
The bot runs as a separate Fly.io service, triggered via HTTP POST.

Authentication:
    Set MCP_API_KEY environment variable to require Bearer token authentication.
    If not set, the server runs without authentication (not recommended for production).
"""

import os
import time
import uuid

import aiohttp
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier


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

# Bot service URL (required for making calls)
BOT_SERVICE_URL = os.environ.get("BOT_SERVICE_URL", "")


# Bot service auth key (for service-to-service auth)
BOT_API_KEY = os.environ.get("BOT_API_KEY", "")


async def create_daily_room(enable_dialout: bool = True) -> dict:
    """Create a Daily room configured for PSTN dial-out.

    Args:
        enable_dialout: If True, configure room for PSTN dial-out (requires paid plan).
                       If False, create a basic room for testing.

    Returns:
        dict with room_name, room_url, token, and dialout_enabled flag
    """
    daily_api_key = os.getenv("DAILY_API_KEY")
    if not daily_api_key:
        raise ValueError("DAILY_API_KEY environment variable not set")

    async with aiohttp.ClientSession() as session:
        # Build room properties
        room_properties: dict = {}

        if enable_dialout:
            room_properties["enable_dialout"] = True

        # Add expiry
        room_properties["exp"] = int(time.time()) + 3600  # 1 hour expiry

        # Create room
        async with session.post(
            "https://api.daily.co/v1/rooms",
            headers={"Authorization": f"Bearer {daily_api_key}"},
            json={"properties": room_properties} if room_properties else {},
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                # If dial-out fails due to plan limitations, try without it
                error_lower = error.lower()
                if enable_dialout and any(
                    x in error_lower for x in ["sip", "dialout", "plan", "display_name"]
                ):
                    return await create_daily_room(enable_dialout=False)
                raise ValueError(f"Failed to create Daily room: {error}")
            room = await resp.json()

        # Get a token for the room
        async with session.post(
            "https://api.daily.co/v1/meeting-tokens",
            headers={"Authorization": f"Bearer {daily_api_key}"},
            json={"properties": {"room_name": room["name"], "is_owner": True}},
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise ValueError(f"Failed to create Daily token: {error}")
            token_data = await resp.json()

    return {
        "room_name": room["name"],
        "room_url": room["url"],
        "token": token_data["token"],
        "dialout_enabled": enable_dialout,
    }


async def delete_daily_room(room_name: str) -> None:
    """Delete a Daily room."""
    daily_api_key = os.getenv("DAILY_API_KEY")
    if not daily_api_key:
        raise ValueError("DAILY_API_KEY environment variable not set")

    async with (
        aiohttp.ClientSession() as session,
        session.delete(
            f"https://api.daily.co/v1/rooms/{room_name}",
            headers={"Authorization": f"Bearer {daily_api_key}"},
        ) as resp,
    ):
        if resp.status not in (200, 204, 404):
            error = await resp.text()
            raise ValueError(f"Failed to delete Daily room: {error}")


async def list_daily_rooms() -> list[dict]:
    """List active Daily rooms."""
    daily_api_key = os.getenv("DAILY_API_KEY")
    if not daily_api_key:
        raise ValueError("DAILY_API_KEY environment variable not set")

    async with (
        aiohttp.ClientSession() as session,
        session.get(
            "https://api.daily.co/v1/rooms",
            headers={"Authorization": f"Bearer {daily_api_key}"},
        ) as resp,
    ):
        if resp.status != 200:
            error = await resp.text()
            raise ValueError(f"Failed to list Daily rooms: {error}")
        data = await resp.json()
        return data.get("data", [])


async def get_daily_room(room_name: str) -> dict | None:
    """Get a specific Daily room."""
    daily_api_key = os.getenv("DAILY_API_KEY")
    if not daily_api_key:
        raise ValueError("DAILY_API_KEY environment variable not set")

    async with (
        aiohttp.ClientSession() as session,
        session.get(
            f"https://api.daily.co/v1/rooms/{room_name}",
            headers={"Authorization": f"Bearer {daily_api_key}"},
        ) as resp,
    ):
        if resp.status == 404:
            return None
        if resp.status != 200:
            error = await resp.text()
            raise ValueError(f"Failed to get Daily room: {error}")
        return await resp.json()


@mcp.tool()
async def make_call(
    phone_number: str,
    instructions: str | None = None,
    secrets: dict[str, str] | None = None,
    caller_id: str | None = None,
    room_name: str | None = None,
) -> dict:
    """
    Initiate an outbound call to the specified phone number using Daily.

    The call starts asynchronously — use get_transcript() to monitor progress
    and send_instruction() to steer the bot mid-call.

    Args:
        phone_number: The phone number to call (E.164 format, e.g., +14155551234)
        instructions: Natural language instructions for the bot describing the goal of the call
                      (e.g., "Schedule a vet appointment for this Saturday after noon")
        secrets: Key-value pairs of sensitive information the bot may need during the call
                 (e.g., {"pet_name": "zipper", "phone_number": "9706330939"}).
                 These are injected into the bot's context but not logged.
        caller_id: The caller ID to display (must be a verified number on your Daily account)
        room_name: Optional room name for the call (auto-generated if not provided)

    Returns:
        A dictionary containing the call details and room information
    """
    try:
        if not BOT_SERVICE_URL:
            raise ValueError("BOT_SERVICE_URL environment variable not set")

        # Create Daily room
        room_info = await create_daily_room()
        dialout_enabled = room_info.get("dialout_enabled", False)

        # Generate call ID
        call_id = room_name or f"paty-call-{uuid.uuid4().hex[:8]}"

        # Trigger bot service via HTTP POST (non-blocking)
        headers = {"Content-Type": "application/json"}
        if BOT_API_KEY:
            headers["Authorization"] = f"Bearer {BOT_API_KEY}"

        payload = {
            "room_url": room_info["room_url"],
            "token": room_info["token"],
            "phone_number": phone_number,
            "caller_id": caller_id,
            "room_name": room_info["room_name"],
            "instructions": instructions,
            "secrets": secrets,
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(
                f"{BOT_SERVICE_URL}/start",
                headers=headers,
                json=payload,
            ) as resp,
        ):
            if resp.status != 200:
                error = await resp.text()
                raise ValueError(f"Failed to start bot: {error}")
            result = await resp.json()

        message = (
            f"Call started to {phone_number}. "
            f"Use get_transcript('{room_info['room_name']}') to monitor."
        )
        if not dialout_enabled:
            message = (
                f"Room created but PSTN dial-out not available on your Daily plan. "
                f"Bot started in room {room_info['room_name']}. "
                f"Upgrade your Daily plan to enable outbound phone calls."
            )

        return {
            "success": True,
            "call_id": call_id,
            "room_name": room_info["room_name"],
            "room_url": room_info["room_url"],
            "phone_number": phone_number,
            "caller_id": caller_id,
            "dialout_enabled": dialout_enabled,
            "message": message,
            "bot_status": result.get("status"),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
async def get_transcript(
    room_name: str,
    since: int = 0,
) -> dict:
    """
    Get real-time transcript events from an active or recently ended call.

    Poll this periodically to monitor the conversation. Use the returned
    next_index as the since parameter on subsequent calls for incremental updates.

    Args:
        room_name: The room name returned by make_call
        since: Event index to start from (use next_index from previous response)

    Returns:
        active: whether the call is still in progress
        events: list of transcript events since the given index
        next_index: pass this as since on next poll
    """
    try:
        if not BOT_SERVICE_URL:
            raise ValueError("BOT_SERVICE_URL environment variable not set")

        headers = {}
        if BOT_API_KEY:
            headers["Authorization"] = f"Bearer {BOT_API_KEY}"

        timeout = aiohttp.ClientTimeout(total=10)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(
                f"{BOT_SERVICE_URL}/transcript/{room_name}",
                headers=headers,
                params={"since": since},
            ) as resp,
        ):
            if resp.status == 404:
                return {
                    "success": False,
                    "error": f"No active session for '{room_name}'",
                }
            if resp.status != 200:
                error = await resp.text()
                raise ValueError(f"Failed to get transcript: {error}")
            data = await resp.json()

        return {
            "success": True,
            "active": data["active"],
            "events": data["events"],
            "next_index": data["next_index"],
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
async def send_instruction(
    room_name: str,
    instruction: str,
    immediate: bool = False,
) -> dict:
    """
    Inject a new instruction into a running call's bot.

    Use this to steer the bot mid-call, e.g., "wrap up the conversation"
    or "ask about their availability on Tuesday instead".

    Args:
        room_name: The room name returned by make_call
        instruction: The instruction text to inject as a system message
        immediate: If True, the bot acts on it right away (interrupts current flow).
                   If False (default), the instruction takes effect on the next turn.

    Returns:
        A dictionary indicating success or failure
    """
    try:
        if not BOT_SERVICE_URL:
            raise ValueError("BOT_SERVICE_URL environment variable not set")

        headers = {"Content-Type": "application/json"}
        if BOT_API_KEY:
            headers["Authorization"] = f"Bearer {BOT_API_KEY}"

        timeout = aiohttp.ClientTimeout(total=10)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(
                f"{BOT_SERVICE_URL}/instruct/{room_name}",
                headers=headers,
                json={"instruction": instruction, "immediate": immediate},
            ) as resp,
        ):
            if resp.status == 404:
                return {
                    "success": False,
                    "error": f"No active session for '{room_name}'",
                }
            if resp.status == 410:
                return {"success": False, "error": "Call has ended"}
            if resp.status == 503:
                return {
                    "success": False,
                    "error": "Pipeline not yet ready, try again shortly",
                }
            if resp.status != 200:
                error = await resp.text()
                raise ValueError(f"Failed to send instruction: {error}")
            data = await resp.json()

        return {
            "success": True,
            "status": data.get("status"),
            "immediate": data.get("immediate"),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
async def end_call(room_name: str) -> dict:
    """
    End an active call by deleting the room.

    Args:
        room_name: The name of the room/call to end

    Returns:
        A dictionary indicating success or failure
    """
    try:
        await delete_daily_room(room_name)

        return {
            "success": True,
            "message": f"Call in room '{room_name}' has been ended",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
async def list_rooms() -> dict:
    """
    List all active rooms/calls.

    Returns:
        A dictionary containing the list of active rooms with their details
    """
    try:
        rooms = await list_daily_rooms()

        paty_rooms = []
        for room in rooms:
            room_info = {
                "name": room.get("name"),
                "url": room.get("url"),
                "created_at": room.get("created_at"),
                "config": room.get("config", {}),
            }
            paty_rooms.append(room_info)

        return {
            "success": True,
            "rooms": paty_rooms,
            "count": len(paty_rooms),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
async def get_call_status(room_name: str) -> dict:
    """
    Get the status of a specific call/room.

    Args:
        room_name: The name of the room to check

    Returns:
        A dictionary containing the room status and call information
    """
    try:
        room = await get_daily_room(room_name)

        if not room:
            return {
                "success": False,
                "error": f"Room '{room_name}' not found",
            }

        return {
            "success": True,
            "room": {
                "name": room.get("name"),
                "url": room.get("url"),
                "created_at": room.get("created_at"),
                "config": room.get("config", {}),
            },
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


if __name__ == "__main__":
    # Use PORT env var for Fly.io compatibility
    port = int(os.environ.get("PORT", 8080))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
