"""
PATY Bot Service - FastAPI HTTP server for the Pipecat voice bot.

Receives requests from the MCP server to start bot instances.
Each bot runs as a background asyncio task within the Cloud Run instance.
"""

import asyncio

from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel

from pipecat_outbound.bot import run_bot

app = FastAPI(title="PATY Bot Service")


class StartRequest(BaseModel):
    room_url: str
    token: str
    phone_number: str
    caller_id: str | None = None
    room_name: str | None = None


@app.post("/start")
async def start(request: StartRequest):
    """Start a bot instance as a background task. Returns immediately."""
    logger.info(f"Starting bot for room {request.room_name}, phone {request.phone_number}")

    async def _run():
        try:
            await run_bot(
                room_url=request.room_url,
                token=request.token,
                phone_number=request.phone_number,
                caller_id=request.caller_id,
                handle_sigint=False,
            )
        except Exception:
            logger.exception(f"Bot error in room {request.room_name}")

    asyncio.create_task(_run())

    return {"status": "started", "room_name": request.room_name}


@app.get("/health")
async def health():
    return {"status": "ok"}
