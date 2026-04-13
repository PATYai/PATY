"""Pipeline builder: resolved services → Pipecat Pipeline + PipelineTask."""

from __future__ import annotations

from typing import Any

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.observers.base_observer import BaseObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)
from pipecat.turns.user_mute import AlwaysUserMuteStrategy


def build_local_transport() -> LocalAudioTransport:
    """Create a local audio transport (mic in, speaker out)."""
    return LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )


def build_pipeline(
    stt: Any,
    llm: Any,
    tts: Any,
    transport: Any,
    persona: str,
    *,
    enable_tracing: bool = True,
    enable_metrics: bool = True,
    observers: list[BaseObserver] | None = None,
) -> tuple[Pipeline, PipelineTask, PipelineRunner]:
    """Build a standard voice agent pipeline.

    Pipeline ordering:
        transport.input → stt → user_agg → llm → tts →
        transport.output → assistant_agg
    """
    messages = [{"role": "system", "content": persona}]
    context = LLMContext(messages)

    user_params = LLMUserAggregatorParams(
        user_mute_strategies=[AlwaysUserMuteStrategy()],
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context, user_params=user_params
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

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=enable_metrics,
        ),
        enable_tracing=enable_tracing,
        observers=observers or [],
    )

    runner = PipelineRunner()
    return pipeline, task, runner
