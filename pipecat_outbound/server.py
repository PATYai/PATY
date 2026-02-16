"""
PATY Bot Service - FastAPI HTTP server for the Pipecat voice bot.

Receives requests from the MCP server to start bot instances.
Returns immediately with room info, then exposes endpoints for
real-time transcript polling and mid-call instruction injection.
"""

import asyncio
import os
from dataclasses import dataclass, field

from fastapi import Depends, FastAPI, HTTPException, Request
from loguru import logger
from pipecat.frames.frames import LLMMessagesAppendFrame
from pipecat.pipeline.task import PipelineTask
from pydantic import BaseModel

from pipecat_outbound.bot import run_bot

app = FastAPI(title="PATY Bot Service")

BOT_API_KEY = os.environ.get("BOT_API_KEY", "")

# Grace period (seconds) to keep session after call ends for final transcript polls
SESSION_GRACE_PERIOD = 60


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


class InstructRequest(BaseModel):
    instruction: str
    immediate: bool = False


@dataclass
class BotSession:
    """Tracks a running bot instance and its transcript buffer."""

    room_name: str
    transcript_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    transcript_buffer: list[dict] = field(default_factory=list)
    pipeline_task: PipelineTask | None = None
    bot_task: asyncio.Task | None = None
    drain_task: asyncio.Task | None = None
    active: bool = True


# Module-level session registry keyed by room_name
active_sessions: dict[str, BotSession] = {}


async def _drain_transcript(session: BotSession) -> None:
    """Background task: drain transcript queue into buffer, clean up after call ends."""
    try:
        while True:
            if session.bot_task is not None and session.bot_task.done():
                # Bot finished — drain remaining events and mark inactive
                while not session.transcript_queue.empty():
                    event = session.transcript_queue.get_nowait()
                    session.transcript_buffer.append(event)
                session.active = False
                break

            try:
                event = await asyncio.wait_for(
                    session.transcript_queue.get(), timeout=1.0
                )
                session.transcript_buffer.append(event)
            except asyncio.TimeoutError:
                continue
    except Exception:
        logger.exception(f"Drain task error for room {session.room_name}")
        session.active = False

    # Grace period before cleanup
    logger.info(
        f"Call ended for {session.room_name}, "
        f"keeping session for {SESSION_GRACE_PERIOD}s"
    )
    await asyncio.sleep(SESSION_GRACE_PERIOD)
    active_sessions.pop(session.room_name, None)
    logger.info(f"Session cleaned up for {session.room_name}")


@app.post("/start", dependencies=[Depends(verify_api_key)])
async def start(request: StartRequest):
    """Start a bot instance. Returns immediately with room info."""
    room_name = request.room_name or "unknown"
    logger.info(f"Starting bot for room {room_name}, phone {request.phone_number}")

    session = BotSession(room_name=room_name)
    active_sessions[room_name] = session

    def on_pipeline_ready(task: PipelineTask):
        session.pipeline_task = task

    bot_task = asyncio.create_task(
        run_bot(
            room_url=request.room_url,
            token=request.token,
            phone_number=request.phone_number,
            caller_id=request.caller_id,
            instructions=request.instructions,
            secrets=request.secrets,
            handle_sigint=False,
            transcript_queue=session.transcript_queue,
            on_pipeline_ready=on_pipeline_ready,
        )
    )
    session.bot_task = bot_task

    # Start background drain task
    session.drain_task = asyncio.create_task(_drain_transcript(session))

    return {"status": "started", "room_name": room_name}


@app.get("/transcript/{room_name}", dependencies=[Depends(verify_api_key)])
async def get_transcript(room_name: str, since: int = 0):
    """Return transcript events since a given index for incremental polling."""
    session = active_sessions.get(room_name)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"No session for room '{room_name}'"
        )

    events = session.transcript_buffer[since:]
    return {
        "active": session.active,
        "events": events,
        "next_index": len(session.transcript_buffer),
    }


@app.post("/instruct/{room_name}", dependencies=[Depends(verify_api_key)])
async def instruct(room_name: str, request: InstructRequest):
    """Inject a system instruction into a running bot's LLM context."""
    session = active_sessions.get(room_name)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"No session for room '{room_name}'"
        )

    if not session.active:
        raise HTTPException(status_code=410, detail="Call has ended")

    if session.pipeline_task is None:
        raise HTTPException(status_code=503, detail="Pipeline not yet ready")

    frame = LLMMessagesAppendFrame(
        messages=[{"role": "system", "content": request.instruction}],
        run_llm=request.immediate,
    )
    await session.pipeline_task.queue_frames([frame])

    logger.info(
        f"Instruction injected into {room_name} "
        f"(immediate={request.immediate}): {request.instruction[:80]}"
    )
    return {"status": "ok", "immediate": request.immediate}


@app.get("/health")
async def health():
    return {"status": "ok"}
