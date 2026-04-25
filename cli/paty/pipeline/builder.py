"""Pipeline builder: resolved services → Pipecat Pipeline + PipelineTask."""

from __future__ import annotations

import warnings
from typing import Any

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.observers.base_observer import BaseObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)

# STTMuteFilter is marked deprecated in favor of user_mute_strategies, but for
# our config (segmented STT + local speaker/mic with acoustic coupling) filtering
# at the STT boundary is the correct layer — it drops echoed mic audio before it
# can be transcribed and delivered to the aggregator late. We accept and silence
# the deprecation warning until pipecat offers an equivalent upstream filter.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from pipecat.processors.filters.stt_mute_filter import (
        STTMuteConfig,
        STTMuteFilter,
        STTMuteStrategy,
    )
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)


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
    input_mute_filter: Any = None,
) -> tuple[Pipeline, PipelineTask, PipelineRunner]:
    """Build a standard voice agent pipeline.

    Pipeline ordering:
        transport.input → [input_mute] → stt_mute → stt → user_agg → llm →
        tts → transport.output → assistant_agg

    ``stt_mute`` is an ``STTMuteFilter`` set to ``ALWAYS`` — it drops mic
    audio and VAD frames for the full duration the bot is speaking, which
    both suppresses acoustic feedback from the speaker → mic loop and
    enforces deliberate turn-taking (no interruption while bot talks).

    ``input_mute_filter`` (optional) drops mic frames whenever the user has
    asked PATY to stop listening — driven from the bus.
    """
    messages = [{"role": "system", "content": persona}]
    context = LLMContext(messages)

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        stt_mute = STTMuteFilter(
            config=STTMuteConfig(strategies={STTMuteStrategy.ALWAYS})
        )

    processors: list[Any] = [transport.input()]
    if input_mute_filter is not None:
        processors.append(input_mute_filter)
    processors.extend(
        [
            stt_mute,
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )
    pipeline = Pipeline(processors)

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
