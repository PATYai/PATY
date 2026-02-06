# pipecat_outbound/bot.py
"""
PATY Voice Bot - Pipecat-based voice agent for outbound calls.

This bot uses Daily for transport and implements the PATY protocol
(Please And Thank You) for polite, low-latency conversations.
"""

import asyncio
import os
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

load_dotenv("../.env.local")
load_dotenv(".env.local")

# PATY system prompt
PATY_SYSTEM_PROMPT = """
You are PATY (pronounced Pah-tee), a helpful, low-latency AI assistant making an outbound call.
You strictly adhere to the PATY protocol (Please And Thank You):
1. Always maintain a warm, extremely polite, and courteous tone.
2. If you need to ask the user for more info, start with 'Please'.
3. When the user provides information, always respond with 'Thank you' or a variation of gratitude.
4. Keep responses concise to maintain low latency, but never sacrifice manners.

Your responses will be read aloud, so keep them conversational and avoid special characters.
Start by greeting the caller warmly and introducing yourself.
"""


class DialoutManager:
    """Manages dialout attempts with retry logic."""

    def __init__(
        self,
        transport: DailyTransport,
        phone_number: str,
        caller_id: str | None = None,
        max_retries: int = 5,
    ):
        self._transport = transport
        self._phone_number = phone_number
        self._caller_id = caller_id
        self._max_retries = max_retries
        self._attempt_count = 0
        self._is_successful = False

    async def attempt_dialout(self) -> bool:
        """Attempt to start a dialout call."""
        if self._attempt_count >= self._max_retries:
            logger.error(
                f"Maximum retry attempts ({self._max_retries}) reached. Giving up on dialout."
            )
            return False

        if self._is_successful:
            logger.debug("Dialout already successful, skipping attempt")
            return False

        self._attempt_count += 1
        logger.info(
            f"Attempting dialout (attempt {self._attempt_count}/{self._max_retries}) to: {self._phone_number}"
        )

        dialout_params: dict[str, Any] = {"phoneNumber": self._phone_number}
        if self._caller_id:
            dialout_params["callerId"] = self._caller_id
            logger.info(f"Using caller ID: {self._caller_id}")

        await self._transport.start_dialout(dialout_params)
        return True

    def mark_successful(self):
        """Mark the dialout as successful."""
        self._is_successful = True

    def should_retry(self) -> bool:
        """Check if another dialout attempt should be made."""
        return self._attempt_count < self._max_retries and not self._is_successful


async def run_bot(
    room_url: str,
    token: str,
    phone_number: str,
    caller_id: str | None = None,
    handle_sigint: bool = True,
) -> None:
    """
    Run the PATY voice bot for an outbound call.

    Args:
        room_url: Daily room URL to join
        token: Daily room token
        phone_number: Phone number to dial (E.164 format)
        caller_id: Optional caller ID to display
        handle_sigint: Whether to handle SIGINT signals
    """
    transport = DailyTransport(
        room_url,
        token,
        "PATY Bot",
        DailyParams(
            api_key=os.getenv("DAILY_API_KEY"),
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

    # Initialize services
    stt = AssemblyAISTTService(api_key=os.getenv("ASSEMBLYAI_API_KEY", ""))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",  # Friendly voice
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # Initialize LLM context with PATY system prompt
    messages = [{"role": "system", "content": PATY_SYSTEM_PROMPT}]
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            audio_in_sample_rate=8000,  # Telephony sample rate
            audio_out_sample_rate=8000,
        ),
    )

    # Initialize dialout manager
    dialout_manager = DialoutManager(transport, phone_number, caller_id)

    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        logger.info("Bot joined Daily room, initiating dialout...")
        await dialout_manager.attempt_dialout()

    @transport.event_handler("on_dialout_answered")
    async def on_dialout_answered(transport, data):
        logger.info(f"Dial-out answered: {data}")
        dialout_manager.mark_successful()
        # Prompt the bot to greet the caller
        await task.queue_frames(
            [context_aggregator.user().get_context_frame()]
        )

    @transport.event_handler("on_dialout_error")
    async def on_dialout_error(transport, data: Any):
        logger.error(f"Dial-out error: {data}")
        if dialout_manager.should_retry():
            await asyncio.sleep(1)  # Brief delay before retry
            await dialout_manager.attempt_dialout()
        else:
            logger.error("No more retries allowed, stopping bot.")
            await task.cancel()

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"Participant left: {participant}, reason: {reason}")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def main():
    """CLI entry point for testing the bot directly."""
    import argparse

    parser = argparse.ArgumentParser(description="PATY Voice Bot")
    parser.add_argument("--room-url", required=True, help="Daily room URL")
    parser.add_argument("--token", required=True, help="Daily room token")
    parser.add_argument("--phone", required=True, help="Phone number to call (E.164)")
    parser.add_argument("--caller-id", help="Caller ID to display")
    args = parser.parse_args()

    await run_bot(
        room_url=args.room_url,
        token=args.token,
        phone_number=args.phone,
        caller_id=args.caller_id,
    )


if __name__ == "__main__":
    asyncio.run(main())
