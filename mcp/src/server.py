"""
PATY MCP Server - Control the PATY voice agent via MCP tools.

This server exposes tools for making outbound calls using Daily and Pipecat.
The bot runs as a separate Fly.io service, triggered via HTTP POST.

Authentication (checked in order):
    1. MCP_AUTH_DISABLED=true  → no auth (dev mode)
    2. CLERK_JWKS_URL + CLERK_ISSUER  → Clerk JWT verification
    3. MCP_API_KEY  → static Bearer token (legacy/testing)
"""

import os
import time
import uuid

import aiohttp
import jwt
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token


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


class ClerkJWTVerifier(TokenVerifier):
    """Verify Clerk-issued JWTs using JWKS (RS256)."""

    def __init__(
        self, jwks_url: str, issuer: str, audience: str | None = None
    ):
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self._jwks_client = jwt.PyJWKClient(jwks_url, cache_keys=True)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"verify_aud": self.audience is not None},
            )
            return AccessToken(
                token=token,
                client_id=payload["sub"],
                scopes=["all"],
                claims=payload,
            )
        except jwt.PyJWTError:
            return None


# Load environment from root .env.local
load_dotenv("../.env.local")
load_dotenv(".env.local")

# Configure authentication (checked in priority order)
auth_disabled = os.environ.get("MCP_AUTH_DISABLED", "").lower() == "true"
clerk_jwks_url = os.environ.get("CLERK_JWKS_URL")
clerk_issuer = os.environ.get("CLERK_ISSUER")
api_key = os.environ.get("MCP_API_KEY")

if auth_disabled:
    auth_provider = None
elif clerk_jwks_url and clerk_issuer:
    auth_provider = ClerkJWTVerifier(
        jwks_url=clerk_jwks_url,
        issuer=clerk_issuer,
        audience=os.environ.get("CLERK_AUDIENCE"),
    )
elif api_key:
    auth_provider = ApiKeyVerifier(api_key)
else:
    raise RuntimeError(
        "Authentication must be configured. Set one of:\n"
        "  - CLERK_JWKS_URL + CLERK_ISSUER (Clerk JWT auth)\n"
        "  - MCP_API_KEY (static API key auth)\n"
        "  - MCP_AUTH_DISABLED=true (no auth, dev only)"
    )

mcp = FastMCP("PATY Control", auth=auth_provider)

# Bot service URL (required for making calls)
BOT_SERVICE_URL = os.environ.get("BOT_SERVICE_URL", "")

# Bot service auth key (for service-to-service auth)
BOT_API_KEY = os.environ.get("BOT_API_KEY", "")


def get_user_id() -> str | None:
    """Extract the authenticated user's ID from the current request context."""
    token = get_access_token()
    return token.client_id if token else None


def _user_room_prefix(user_id: str) -> str:
    """Return the room name prefix for a given user."""
    return f"paty-{user_id[:8]}-"


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

        user_id = get_user_id()

        # Create Daily room
        room_info = await create_daily_room()
        dialout_enabled = room_info.get("dialout_enabled", False)

        # Generate call ID, scoped to user when authenticated
        if room_name:
            call_id = room_name
        elif user_id:
            call_id = f"{_user_room_prefix(user_id)}{uuid.uuid4().hex[:8]}"
        else:
            call_id = f"paty-call-{uuid.uuid4().hex[:8]}"

        # Trigger bot service via HTTP POST
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
            "user_id": user_id,
        }

        # Use a long timeout since the bot blocks until the call ends
        timeout = aiohttp.ClientTimeout(total=3600)
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

        # Build response message
        if dialout_enabled:
            message = f"Call initiated to {phone_number}"
        else:
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
        # Scope check: authenticated users can only end their own rooms
        user_id = get_user_id()
        if user_id and not room_name.startswith(_user_room_prefix(user_id)):
            return {
                "success": False,
                "error": f"Room '{room_name}' does not belong to you",
            }

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
        user_id = get_user_id()
        prefix = _user_room_prefix(user_id) if user_id else None

        paty_rooms = []
        for room in rooms:
            name = room.get("name", "")
            # Filter to only this user's rooms when authenticated
            if prefix and not name.startswith(prefix):
                continue
            room_info = {
                "name": name,
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
        # Scope check: authenticated users can only see their own rooms
        user_id = get_user_id()
        if user_id and not room_name.startswith(_user_room_prefix(user_id)):
            return {
                "success": False,
                "error": f"Room '{room_name}' not found",
            }

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
