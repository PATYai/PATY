"""Tests for the InputMuteFilter."""

from __future__ import annotations

import pytest
from pipecat.frames.frames import (
    InputAudioRawFrame,
    LLMTextFrame,
    UserMuteStartedFrame,
    UserMuteStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from paty.pipeline.mute import InputMuteFilter


def _audio() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00\x00", sample_rate=16000, num_channels=1)


@pytest.fixture
def filt_and_pushed():
    """A filter with push_frame patched to capture forwarded frames."""
    filt = InputMuteFilter()
    pushed: list = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    filt.push_frame = capture  # type: ignore[method-assign]
    return filt, pushed


class TestInputMuteFilter:
    def test_starts_unmuted(self):
        assert InputMuteFilter().muted is False

    async def test_toggle_pushes_mute_started(self, filt_and_pushed):
        filt, pushed = filt_and_pushed
        assert await filt.toggle() is True
        assert filt.muted is True
        assert any(isinstance(f, UserMuteStartedFrame) for f in pushed)

    async def test_set_mute_off_pushes_mute_stopped(self, filt_and_pushed):
        filt, pushed = filt_and_pushed
        await filt.set_mute(True)
        pushed.clear()
        await filt.set_mute(False)
        assert any(isinstance(f, UserMuteStoppedFrame) for f in pushed)

    async def test_no_op_when_state_unchanged(self, filt_and_pushed):
        filt, pushed = filt_and_pushed
        await filt.set_mute(False)
        assert pushed == []

    async def test_passes_mic_frames_when_unmuted(self, filt_and_pushed):
        filt, pushed = filt_and_pushed
        await filt.process_frame(_audio(), FrameDirection.DOWNSTREAM)
        assert any(isinstance(f, InputAudioRawFrame) for f in pushed)

    async def test_drops_mic_audio_and_speech_when_muted(self, filt_and_pushed):
        filt, pushed = filt_and_pushed
        await filt.set_mute(True)
        pushed.clear()
        await filt.process_frame(_audio(), FrameDirection.DOWNSTREAM)
        await filt.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        await filt.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        assert not any(
            isinstance(
                f,
                InputAudioRawFrame
                | UserStartedSpeakingFrame
                | UserStoppedSpeakingFrame,
            )
            for f in pushed
        )

    async def test_non_mic_frames_pass_when_muted(self, filt_and_pushed):
        filt, pushed = filt_and_pushed
        await filt.set_mute(True)
        pushed.clear()
        await filt.process_frame(LLMTextFrame(text="ok"), FrameDirection.DOWNSTREAM)
        assert any(isinstance(f, LLMTextFrame) for f in pushed)
