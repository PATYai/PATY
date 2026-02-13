"""
PATY Bot Service - FastAPI HTTP server for the Pipecat voice bot.

Receives requests from the MCP server to start bot instances.
The bot runs in the request handler so the HTTP connection stays open
for the duration of the call, keeping the Fly.io instance alive.
"""

import os

from fastapi import Depends, FastAPI, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from pipecat_outbound.bot import run_bot

app = FastAPI(title="PATY Bot Service")

BOT_API_KEY = os.environ.get("BOT_API_KEY", "")


async def verify_api_key(request: Request):
    """Verify Bearer token matches BOT_API_KEY. Skipped if key is unset."""
    if not BOT_API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != BOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class StartRequest(BaseModel):
    room_url: str
    token: str
    phone_number: str
    caller_id: str | None = None
    room_name: str | None = None
    instructions: str | None = None
    secrets: dict[str, str] | None = None


@app.post("/start", dependencies=[Depends(verify_api_key)])
async def start(request: StartRequest):
    """Start a bot instance. Blocks until the call ends."""
    logger.info(f"Starting bot for room {request.room_name}, phone {request.phone_number}")

    try:
        await run_bot(
            room_url=request.room_url,
            token=request.token,
            phone_number=request.phone_number,
            caller_id=request.caller_id,
            instructions=request.instructions,
            secrets=request.secrets,
            handle_sigint=False,
        )
    except Exception:
        logger.exception(f"Bot error in room {request.room_name}")
        return {"status": "error", "room_name": request.room_name}

    return {"status": "completed", "room_name": request.room_name}


@app.get("/health")
async def health():
    return {"status": "ok"}
