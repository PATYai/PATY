# pipecat_outbound/bot.py
"""
PATY Voice Bot - Pipecat-based voice agent for outbound calls.

This bot uses Daily for transport and implements the PATY protocol
(Please And Thank You) for polite, low-latency conversations.
"""

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from loguru import logger
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.observers.loggers.metrics_log_observer import MetricsLogObserver
from pipecat.observers.turn_tracking_observer import TurnTrackingObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.assemblyai.models import AssemblyAIConnectionParams
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.turns.user_turn_strategies import (
    TranscriptionUserTurnStartStrategy,
    TranscriptionUserTurnStopStrategy,
    UserTurnStrategies,
    VADUserTurnStartStrategy,
)
from pipecat.utils.tracing.setup import setup_tracing

from pipecat_outbound.prompt import build_system_prompt

load_dotenv("../.env.local")
load_dotenv(".env.local")


def _load_config() -> dict:
    """Load telephony.yaml config, resolving ${ENV_VAR} references."""
    config_path = Path(__file__).parent / "telephony.yaml"
    if not config_path.exists():
        return {}
    raw = config_path.read_text()
    # Resolve ${VAR} placeholders from environment
    import re

    def _resolve(match):
        return os.getenv(match.group(1), match.group(0))

    resolved = re.sub(r"\$\{(\w+)}", _resolve, raw)
    return yaml.safe_load(resolved) or {}


CONFIG = _load_config()


# OpenTelemetry tracing — reads OTEL_EXPORTER_OTLP_ENDPOINT and
# OTEL_EXPORTER_OTLP_HEADERS from env automatically.
# Local: defaults to localhost:4317 (Jaeger). Prod: set env vars for Honeycomb.
setup_tracing(os.getenv("OTEL_SERVICE_NAME", "paty-bot"), exporter=OTLPSpanExporter())


class TranscriptObserver(BaseObserver):
    """Observer that captures conversation turns and pushes them to a queue.

    Listens for TranscriptionFrame (user speech) and LLMTextFrame/LLMFullResponseEndFrame
    (assistant responses) to reconstruct conversation turns as NDJSON-ready dicts.
    """

    def __init__(self, queue: asyncio.Queue, **kwargs):
        super().__init__(**kwargs)
        self._queue = queue
        self._turn_number = 0
        self._current_user_text = ""
        self._current_assistant_chunks: list[str] = []

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            # Accumulate user speech (multiple transcription frames per turn)
            self._current_user_text = frame.text
            self._turn_number += 1
            event = {
                "type": "transcript",
                "turn": self._turn_number,
                "role": "user",
                "text": frame.text,
            }
            logger.debug(f"Transcript event: {json.dumps(event)}")
            await self._queue.put(event)

        elif isinstance(frame, LLMTextFrame):
            self._current_assistant_chunks.append(frame.text)

        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._current_assistant_chunks:
                full_response = "".join(self._current_assistant_chunks)
                event = {
                    "type": "transcript",
                    "turn": self._turn_number,
                    "role": "assistant",
                    "text": full_response,
                }
                logger.debug(f"Transcript event: {json.dumps(event)}")
                await self._queue.put(event)
                self._current_assistant_chunks = []


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
    target_phone: str,
    target_who: str,
    goal: str,
    caller_id: str | None = None,
    impersonate: bool = False,
    persona: str | None = None,
    secrets: dict[str, str] | None = None,
    handle_sigint: bool = True,
    transcript_queue: asyncio.Queue | None = None,
    on_pipeline_ready: Callable[[PipelineTask], None] | None = None,
    transport_override=None,
    stt_override=None,
    tts_override=None,
    llm_override=None,
) -> None:
    """
    Run the PATY voice bot for an outbound call.

    Args:
        room_url: Daily room URL to join
        token: Daily room token
        target_phone: Phone number to dial (E.164 format)
        target_who: Name/description of who is being called
        caller_id: Optional caller ID to display
        goal: Natural language description of the call's objective
        impersonate: Whether the bot should present itself as a persona
        persona: Who the bot is impersonating (required when impersonate=True)
        secrets: Key-value pairs of sensitive info the bot may reference during the call
        handle_sigint: Whether to handle SIGINT signals
        transcript_queue: Optional queue to receive real-time transcript events
        on_pipeline_ready: Optional callback invoked with the PipelineTask once created
        transport_override: Optional transport to use instead of DailyTransport (for testing)
        stt_override: Optional STT service to use instead of AssemblyAI (for testing)
        tts_override: Optional TTS service to use instead of Cartesia (for testing)
        llm_override: Optional LLM service to use instead of OpenAI (for testing)
    """
    if transport_override is not None:
        transport = transport_override
    else:
        transport = DailyTransport(
            room_url,
            token,
            "PATY Bot",
            DailyParams(
                api_key=os.getenv("DAILY_API_KEY"),
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )

    # Initialize services
    if stt_override is not None:
        stt = stt_override
    else:
        stt = AssemblyAISTTService(
            api_key=os.getenv("ASSEMBLYAI_API_KEY", ""),
            connection_params=AssemblyAIConnectionParams(sample_rate=8000),
        )

    cartesia_config = CONFIG.get("tts", {}).get("provider", {}).get("cartesia", {})
    if tts_override is not None:
        tts = tts_override
    else:
        tts = CartesiaTTSService(
            api_key=cartesia_config.get("api_key") or os.getenv("CARTESIA_API_KEY", ""),
            voice_id=cartesia_config.get(
                "voice_id", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
            ),
        )

    if llm_override is not None:
        llm = llm_override
    else:
        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # Build system prompt
    system_prompt = build_system_prompt(
        target_who=target_who,
        goal=goal,
        impersonate=impersonate,
        persona=persona,
        secrets=secrets,
    )

    # Initialize LLM context with system prompt
    messages = [{"role": "system", "content": system_prompt}]
    context = LLMContext(messages)
    # Conservative VAD settings for PSTN — higher confidence and start_secs
    # to avoid echo triggering false interruptions.
    vad = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.75,
            start_secs=0.3,
            stop_secs=0.7,
            min_volume=0.65,
        )
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad,
            user_turn_strategies=UserTurnStrategies(
                start=[
                    VADUserTurnStartStrategy(),
                    TranscriptionUserTurnStartStrategy(use_interim=True),
                ],
                stop=[TranscriptionUserTurnStopStrategy(timeout=0.5)],
            ),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    turn_observer = TurnTrackingObserver()

    @turn_observer.event_handler("on_turn_ended")
    async def on_turn_ended(observer, turn_number, duration, was_interrupted):
        status = "interrupted" if was_interrupted else "completed"
        logger.info(f"Turn {turn_number} {status} after {duration:.2f}s")

    observers = [MetricsLogObserver(), turn_observer]
    if transcript_queue is not None:
        observers.append(TranscriptObserver(transcript_queue))

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            audio_in_sample_rate=8000,  # Telephony sample rate
            audio_out_sample_rate=8000,
        ),
        enable_tracing=True,
        observers=observers,
    )

    if on_pipeline_ready is not None:
        on_pipeline_ready(task)

    # Initialize dialout manager (skip when using transport override for testing)
    if transport_override is None:
        dialout_manager = DialoutManager(transport, target_phone, caller_id)

        @transport.event_handler("on_joined")
        async def on_joined(transport, data):
            logger.info("Bot joined Daily room, initiating dialout...")
            await dialout_manager.attempt_dialout()

        @transport.event_handler("on_dialout_answered")
        async def on_dialout_answered(transport, data):
            logger.info(f"Dial-out answered: {data}")
            dialout_manager.mark_successful()
            if transcript_queue is not None:
                await transcript_queue.put(
                    {"type": "status", "event": "dialout_answered"}
                )
            # Prompt the bot to greet the caller
            from pipecat.frames.frames import LLMRunFrame

            await task.queue_frames([LLMRunFrame()])

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
    parser.add_argument(
        "--target-phone", required=True, help="Phone number to call (E.164)"
    )
    parser.add_argument(
        "--target-who", required=True, help="Name/description of who is being called"
    )
    parser.add_argument("--caller-id", help="Caller ID to display")
    parser.add_argument("--goal", help="Goal for the call")
    parser.add_argument(
        "--impersonate", action="store_true", help="Present as a persona"
    )
    parser.add_argument(
        "--persona", help="Who the bot is impersonating (required with --impersonate)"
    )
    parser.add_argument(
        "--secret",
        action="append",
        help="Secret key=value pair (can be repeated)",
    )
    args = parser.parse_args()

    secrets = None
    if args.secret:
        secrets = {}
        for s in args.secret:
            key, _, value = s.partition("=")
            secrets[key] = value

    await run_bot(
        room_url=args.room_url,
        token=args.token,
        target_phone=args.target_phone,
        target_who=args.target_who,
        caller_id=args.caller_id,
        goal=args.goal,
        impersonate=args.impersonate,
        persona=args.persona,
        secrets=secrets,
    )


if __name__ == "__main__":
    asyncio.run(main())
