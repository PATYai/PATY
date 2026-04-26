"""Tests for the avatar widget — built-in fallback vs. PAK-supplied faces.

These tests poke at private helpers because the public ``render_avatar``
returns a Rich ``Panel`` that's awkward to assert against directly.  The
private ``_resolve_face`` is the actual decision logic worth testing.
"""

from __future__ import annotations

from paty.tui.theme import DAY
from paty.tui.widgets.avatar import _FACES, _resolve_face, render_avatar


class TestResolveFace:
    def test_no_override_uses_builtin(self):
        assert _resolve_face("idle", None) == _FACES["idle"]
        assert _resolve_face("listening", None) == _FACES["listening"]

    def test_override_wins(self):
        override = {"idle": "(*-*)"}
        assert _resolve_face("idle", override) == "(*-*)"

    def test_partial_override_falls_back_per_state(self):
        """A PAK that only ships idle.txt should still get default
        listening/thinking/speaking faces — not blanks."""
        override = {"idle": "(*-*)"}
        assert _resolve_face("idle", override) == "(*-*)"
        assert _resolve_face("listening", override) == _FACES["listening"]

    def test_unknown_state_falls_back_to_builtin_idle(self):
        """An unknown agent state (shouldn't happen — the bus enum is fixed)
        falls back to the built-in idle face.  The override is consulted only
        for the requested state, never as a generic catch-all."""
        assert _resolve_face("dancing", None) == _FACES["idle"]
        assert _resolve_face("dancing", {"idle": "OVR"}) == _FACES["idle"]


class TestRenderAvatar:
    """Smoke tests for the panel renderer.  We only assert the chosen face
    is present in the panel's text — Rich layout details are out of scope."""

    def _panel_text(self, panel) -> str:
        # Walk the renderable into a plain string by joining all visible
        # text segments.
        parts: list[str] = []

        def collect(node) -> None:
            if hasattr(node, "_text"):
                parts.extend(str(s) for s in node._text)
            if hasattr(node, "renderable"):
                collect(node.renderable)
            if hasattr(node, "renderables"):
                for r in node.renderables:
                    collect(r)

        collect(panel)
        return " ".join(parts)

    def test_uses_override_face_when_present(self):
        panel = render_avatar("speaking", DAY, state_faces={"speaking": "<<custom>>"})
        assert "<<custom>>" in self._panel_text(panel)

    def test_falls_back_to_builtin_without_override(self):
        panel = render_avatar("speaking", DAY, state_faces=None)
        assert _FACES["speaking"] in self._panel_text(panel)

    def test_input_state_takes_precedence(self):
        """typing/clearing are TUI-internal and must not be PAK-overridable."""
        panel = render_avatar(
            "idle",
            DAY,
            input_state="typing",
            state_faces={"idle": "<<should not appear>>"},
        )
        text = self._panel_text(panel)
        assert "<<should not appear>>" not in text
