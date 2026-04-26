"""Tests for the TUI's bus dispatcher — specifically that session.started
populates the avatar slot and that the absence of an avatar is preserved.
"""

from __future__ import annotations

import json

from paty.tui.app import UIState, _dispatch


def _event(etype: str, **data) -> str:
    return json.dumps(
        {
            "v": 1,
            "seq": 1,
            "ts_ms": 0,
            "session_id": "test",
            "type": etype,
            "data": data,
        }
    )


class TestSessionStartedAvatar:
    def test_populates_session_avatar_when_present(self):
        state = UIState()
        avatar = {"idle": "(*-*)", "speaking": "(*o*)"}
        handled = _dispatch(
            state,
            _event(
                "session.started",
                persona="x",
                profile="auto",
                platform="mlx",
                stt="X",
                llm="X",
                tts="X",
                avatar=avatar,
            ),
        )
        assert handled is True
        assert state.session_avatar == avatar

    def test_leaves_session_avatar_none_when_absent(self):
        state = UIState()
        handled = _dispatch(
            state,
            _event(
                "session.started",
                persona="x",
                profile="auto",
                platform="mlx",
                stt="X",
                llm="X",
                tts="X",
            ),
        )
        assert handled is True
        assert state.session_avatar is None

    def test_explicit_null_avatar_resets_to_none(self):
        state = UIState(session_avatar={"idle": "stale"})
        _dispatch(
            state,
            _event(
                "session.started",
                persona="x",
                profile="auto",
                platform="mlx",
                stt="X",
                llm="X",
                tts="X",
                avatar=None,
            ),
        )
        assert state.session_avatar is None

    def test_non_dict_avatar_payload_falls_through_to_none(self):
        """Defensive: a malformed payload shouldn't crash the TUI."""
        state = UIState()
        _dispatch(
            state,
            _event(
                "session.started",
                persona="x",
                profile="auto",
                platform="mlx",
                stt="X",
                llm="X",
                tts="X",
                avatar="garbage",
            ),
        )
        assert state.session_avatar is None
