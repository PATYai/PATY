"""Inject typed messages into a running pipeline as if they were spoken.

Sits between ``stt`` and the user aggregator so its frames bypass STT entirely
but still drive the same turn boundaries — interrupting the agent and
delivering a ``TranscriptionFrame`` that the aggregator commits to the LLM
context. Placement after ``InputMuteFilter`` is deliberate: typed input is a
separate channel from the mic and must remain available while muted.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.time import time_now_iso8601

USER_ID = "text-input"


class TextInputInjector(FrameProcessor):
    """Pass-through processor that can inject a typed user turn on demand."""

    async def inject(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        await self.push_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
        await self.push_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        await self.push_frame(
            TranscriptionFrame(
                text=text,
                user_id=USER_ID,
                timestamp=time_now_iso8601(),
            ),
            FrameDirection.DOWNSTREAM,
        )
        await self.push_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
