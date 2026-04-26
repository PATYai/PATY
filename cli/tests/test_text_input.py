"""Tests for the TextInputInjector."""

from __future__ import annotations

import pytest
from pipecat.frames.frames import (
    InterruptionFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from paty.pipeline.text_input import TextInputInjector


@pytest.fixture
def injector_and_pushed():
    """An injector with push_frame patched to capture forwarded frames."""
    inj = TextInputInjector()
    pushed: list = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append((frame, direction))

    inj.push_frame = capture  # type: ignore[method-assign]
    return inj, pushed


class TestTextInputInjector:
    async def test_inject_pushes_full_turn_sequence(self, injector_and_pushed):
        inj, pushed = injector_and_pushed
        await inj.inject("hello there")

        types = [type(f) for f, _ in pushed]
        assert types == [
            InterruptionFrame,
            UserStartedSpeakingFrame,
            TranscriptionFrame,
            UserStoppedSpeakingFrame,
        ]
        transcription = pushed[2][0]
        assert transcription.text == "hello there"

    async def test_inject_pushes_downstream(self, injector_and_pushed):
        inj, pushed = injector_and_pushed
        await inj.inject("hi")
        assert all(direction == FrameDirection.DOWNSTREAM for _, direction in pushed)

    async def test_empty_text_is_a_noop(self, injector_and_pushed):
        inj, pushed = injector_and_pushed
        await inj.inject("")
        await inj.inject("   ")
        assert pushed == []

    async def test_strips_whitespace(self, injector_and_pushed):
        inj, pushed = injector_and_pushed
        await inj.inject("  hi  ")
        transcription = pushed[2][0]
        assert transcription.text == "hi"
