"""User-controlled mic mute, expressed in Pipecat's native frame vocabulary.

The filter sits right after ``transport.input()`` and is the single owner of
mute state for the pipeline. On a transition it pushes pipecat's
``UserMuteStarted/UserMuteStoppedFrame`` so any downstream processor (or the
bus observer) can react without taking a direct reference to this object.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    UserMuteStartedFrame,
    UserMuteStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# Frames the filter sees moving downstream from ``transport.input()``.
# Transcription frames are produced downstream of this filter and never
# flow through it.
_SUPPRESSED = (
    InterruptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    InputAudioRawFrame,
)


class InputMuteFilter(FrameProcessor):
    """Drops user-input frames downstream while muted."""

    def __init__(self, muted: bool = False) -> None:
        super().__init__()
        self._muted = bool(muted)

    @property
    def muted(self) -> bool:
        return self._muted

    async def toggle(self) -> bool:
        return await self.set_mute(not self._muted)

    async def set_mute(self, muted: bool) -> bool:
        muted = bool(muted)
        if muted == self._muted:
            return self._muted
        self._muted = muted
        boundary = UserMuteStartedFrame() if muted else UserMuteStoppedFrame()
        await self.push_frame(boundary, FrameDirection.DOWNSTREAM)
        return self._muted

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if self._muted and isinstance(frame, _SUPPRESSED):
            return
        await self.push_frame(frame, direction)
