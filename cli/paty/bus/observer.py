"""Translates Pipecat pipeline frames into PATY bus events."""

from __future__ import annotations

from collections import deque

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    MetricsFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    UserMuteStartedFrame,
    UserMuteStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import (
    ProcessingMetricsData,
    TTFBMetricsData,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

from paty.bus.events import (
    AgentState,
    AudioStream,
    ErrorData,
    EventType,
    MetricsTick,
    ResponseCompleted,
    SpeechStopped,
    StateChanged,
    Transcript,
)
from paty.bus.server import WebSocketBus

_DEDUP_SIZE = 4096

_STT_KEYWORDS = ("stt", "whisper", "assemblyai", "deepgram")
_LLM_KEYWORDS = ("llm", "openai", "ollama", "llama")
_TTS_KEYWORDS = ("tts", "cartesia", "kokoro", "mlxaudio")


def _classify(processor: str) -> str:
    lower = processor.lower()
    if any(k in lower for k in _STT_KEYWORDS):
        return "stt"
    if any(k in lower for k in _LLM_KEYWORDS):
        return "llm"
    if any(k in lower for k in _TTS_KEYWORDS):
        return "tts"
    return "unknown"


class BusObserver(BaseObserver):
    """Observer that republishes Pipecat frames to a WebSocketBus.

    Frames are observed on every pipeline edge, so a small LRU of recently
    seen frame ids deduplicates so each logical event is emitted once.

    Agent state (idle/listening/thinking/speaking) is derived from the
    speaking/thinking flags and published on transitions.
    """

    def __init__(self, bus: WebSocketBus, **kwargs):
        super().__init__(**kwargs)
        self._bus = bus
        self._seen: deque[int] = deque(maxlen=_DEDUP_SIZE)
        self._seen_set: set[int] = set()

        self._user_speaking = False
        self._bot_speaking = False
        self._llm_active = False
        self._user_muted = False
        self._state: AgentState = AgentState.IDLE

        self._user_speech_start_ms: int | None = None
        self._bot_speech_start_ms: int | None = None
        self._response_text: list[str] = []

    def _first_time_seeing(self, frame_id: int) -> bool:
        if frame_id in self._seen_set:
            return False
        if len(self._seen) == _DEDUP_SIZE:
            self._seen_set.discard(self._seen[0])
        self._seen.append(frame_id)
        self._seen_set.add(frame_id)
        return True

    def _recompute_state(self) -> None:
        if self._bot_speaking:
            new_state = AgentState.SPEAKING
        elif self._user_speaking:
            new_state = AgentState.LISTENING
        elif self._llm_active:
            new_state = AgentState.THINKING
        else:
            new_state = AgentState.IDLE
        if new_state != self._state:
            self._state = new_state
            self._bus.publish(EventType.STATE_CHANGED, StateChanged(state=new_state))

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame

        # Audio frames dedupe per-edge too — emit once from the first push.
        if isinstance(frame, InputAudioRawFrame):
            if self._user_muted:
                return
            if self._first_time_seeing(frame.id):
                self._bus.publish_audio(
                    AudioStream.MIC,
                    frame.sample_rate,
                    frame.num_channels,
                    bytes(frame.audio),
                )
            return

        if isinstance(frame, OutputAudioRawFrame):
            if self._first_time_seeing(frame.id):
                self._bus.publish_audio(
                    AudioStream.AGENT,
                    frame.sample_rate,
                    frame.num_channels,
                    bytes(frame.audio),
                )
            return

        if not self._first_time_seeing(frame.id):
            return

        if isinstance(frame, UserMuteStartedFrame):
            self._user_muted = True
            if self._user_speaking:
                self._user_speaking = False
                self._user_speech_start_ms = None
                self._recompute_state()
            return

        if isinstance(frame, UserMuteStoppedFrame):
            self._user_muted = False
            return

        if isinstance(frame, UserStartedSpeakingFrame):
            if self._user_muted:
                return
            self._user_speaking = True
            self._user_speech_start_ms = self._bus.ts_ms()
            self._bus.publish(EventType.USER_SPEECH_STARTED)
            self._recompute_state()

        elif isinstance(frame, UserStoppedSpeakingFrame):
            if self._user_muted:
                return
            self._user_speaking = False
            duration_ms = None
            if self._user_speech_start_ms is not None:
                duration_ms = self._bus.ts_ms() - self._user_speech_start_ms
                self._user_speech_start_ms = None
            self._bus.publish(
                EventType.USER_SPEECH_STOPPED,
                SpeechStopped(duration_ms=duration_ms),
            )
            self._recompute_state()

        elif isinstance(frame, InterimTranscriptionFrame):
            self._bus.publish(
                EventType.USER_TRANSCRIPT_PARTIAL, Transcript(text=frame.text)
            )

        elif isinstance(frame, TranscriptionFrame):
            self._bus.publish(
                EventType.USER_TRANSCRIPT_FINAL, Transcript(text=frame.text)
            )

        elif isinstance(frame, LLMFullResponseStartFrame):
            self._llm_active = True
            self._response_text = []
            self._bus.publish(EventType.AGENT_THINKING_STARTED)
            self._recompute_state()

        elif isinstance(frame, LLMTextFrame):
            self._response_text.append(frame.text)
            self._bus.publish(
                EventType.AGENT_RESPONSE_DELTA, Transcript(text=frame.text)
            )

        elif isinstance(frame, LLMFullResponseEndFrame):
            self._llm_active = False
            full = "".join(self._response_text)
            self._response_text = []
            self._bus.publish(
                EventType.AGENT_RESPONSE_COMPLETED,
                ResponseCompleted(text=full),
            )
            self._recompute_state()

        elif isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._bot_speech_start_ms = self._bus.ts_ms()
            self._bus.publish(EventType.AGENT_SPEECH_STARTED)
            self._recompute_state()

        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            duration_ms = None
            if self._bot_speech_start_ms is not None:
                duration_ms = self._bus.ts_ms() - self._bot_speech_start_ms
                self._bot_speech_start_ms = None
            self._bus.publish(
                EventType.AGENT_SPEECH_STOPPED,
                SpeechStopped(duration_ms=duration_ms),
            )
            self._recompute_state()

        elif isinstance(frame, MetricsFrame):
            self._emit_metrics(frame, source_name=getattr(data.source, "name", None))

        elif isinstance(frame, ErrorFrame):
            self._bus.publish(
                EventType.ERROR,
                ErrorData(
                    message=str(frame.error),
                    recoverable=not getattr(frame, "fatal", False),
                ),
            )

    def _emit_metrics(self, frame: MetricsFrame, source_name: str | None) -> None:
        # A MetricsFrame crosses every downstream edge; attribute only the
        # first hop (source matches the processor that emitted the entry)
        # so one tick = one publish.
        tick_kwargs: dict[str, float | str] = {}
        for entry in frame.data:
            if source_name and source_name != entry.processor:
                continue
            category = _classify(entry.processor)
            if isinstance(entry, TTFBMetricsData):
                tick_kwargs["ttfb_ms"] = entry.value * 1000
                tick_kwargs[f"{category}_ms"] = entry.value * 1000
                tick_kwargs["processor"] = entry.processor
            elif isinstance(entry, ProcessingMetricsData) and category == "llm":
                tick_kwargs["llm_ms"] = entry.value * 1000
                tick_kwargs["processor"] = entry.processor
        if tick_kwargs:
            self._bus.publish(EventType.METRICS_TICK, MetricsTick(**tick_kwargs))
