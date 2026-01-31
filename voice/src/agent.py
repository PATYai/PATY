import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    get_job_context,
    inference,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("paty-voice")
logger.setLevel(logging.INFO)

# Load environment from root .env.local
load_dotenv("../.env.local")
load_dotenv(".env.local")

# Path to participant.json (at project root)
PARTICIPANT_CONFIG_PATH = os.environ.get(
    "PARTICIPANT_CONFIG_PATH", "../participant.json"
)


def load_dial_info() -> dict:
    """Load dial info from participant.json"""
    config_path = PARTICIPANT_CONFIG_PATH
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
            You are PATY (prounounced Pah-tee), a helpful, low-latency AI assistant making an outbound call.
            You strictly adhere to the PATY protocol (Please And Thank You):
            1. Always maintain a warm, extremely polite, and courteous tone.
            2. If you need to ask the user for more info, start with 'Please'.
            3. When the user provides information, always respond with 'Thank you' or a variation of gratitude.
            4. Keep responses concise to maintain low latency, but never sacrifice manners.

            Start by greeting the user warmly and introducing yourself.
            When the user wants to end the call, use the end_call tool.
        """
        )
        self.participant: rtc.RemoteParticipant | None = None

    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant

    async def hangup(self):
        """Helper function to hang up the call by deleting the room"""
        job_ctx = get_job_context()
        await job_ctx.api.room.delete_room(
            api.DeleteRoomRequest(room=job_ctx.room.name)
        )

    @function_tool()
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call"""
        logger.info(
            f"ending the call for {self.participant.identity if self.participant else 'unknown'}"
        )

        # Let the agent finish speaking
        current_speech = ctx.session.current_speech
        if current_speech:
            await current_speech.wait_for_playout()

        await self.hangup()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect()

    # Load dial info from participant.json or job metadata
    dial_info = load_dial_info()

    # Override with job metadata if available (from MCP dispatch)
    if ctx.job.metadata:
        try:
            metadata = json.loads(ctx.job.metadata)
            dial_info.update(metadata)
        except json.JSONDecodeError:
            pass

    outbound_trunk_id = dial_info.get("sip_trunk_id") or os.getenv(
        "SIP_OUTBOUND_TRUNK_ID"
    )
    phone_number = dial_info.get("sip_call_to")
    participant_identity = dial_info.get("participant_identity", phone_number)

    if not phone_number:
        logger.error("No phone number provided in participant.json or job metadata")
        ctx.shutdown()
        return

    agent = Assistant()

    # Set up voice AI pipeline
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-streaming", language="en"),
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
        tts=inference.TTS(
            model="cartesia/sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # Start the session first before dialing, to ensure we don't miss anything when user picks up
    session_started = asyncio.create_task(
        session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )
    )

    # Dial the phone number
    sip_number = dial_info.get("sip_number")  # Caller ID
    logger.info(f"dialing {phone_number} from {sip_number}...")
    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=outbound_trunk_id,
                sip_call_to=phone_number,
                sip_number=sip_number,  # Set the caller ID
                participant_identity=participant_identity,
                participant_name=dial_info.get("participant_name", ""),
                wait_until_answered=True,
            )
        )

        # Wait for the agent session to start and participant to join
        await session_started
        participant = await ctx.wait_for_participant(identity=participant_identity)
        logger.info(f"participant joined: {participant.identity}")

        agent.set_participant(participant)

    except api.TwirpError as e:
        logger.error(
            f"error creating SIP participant: {e.message}, "
            f"SIP status: {e.metadata.get('sip_status_code')} "
            f"{e.metadata.get('sip_status')}"
        )
        ctx.shutdown()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="paty-voice",
        )
    )
