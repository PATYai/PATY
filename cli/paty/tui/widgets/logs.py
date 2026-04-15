"""Scrolling log panel widget with selectable text and copy support."""

from __future__ import annotations

from typing import ClassVar

from textual.binding import BindingType
from textual.widgets import TextArea

_LEVEL_PREFIX = {
    "info": "",
    "success": "[OK] ",
    "warning": "[WARN] ",
    "error": "[ERROR] ",
}


class LogsWidget(TextArea):
    """Read-only log panel with text selection and yank-to-clipboard."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("y", "copy_all", "Copy logs"),
    ]

    DEFAULT_CSS = """
    LogsWidget {
        height: 1fr;
        border-top: solid $primary-background;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", read_only=True, **kwargs)
        self._lines: list[str] = []

    def on_mount(self) -> None:
        self.border_title = "Logs"

    def log_message(self, message: str, level: str = "info") -> None:
        prefix = _LEVEL_PREFIX.get(level, "")
        full = f"{prefix}{message}"
        self._lines.append(full)
        # TextArea rejects insert() when read_only — toggle it briefly
        self.read_only = False
        self.insert(full + "\n", self.document.end)
        self.read_only = True
        self.scroll_end(animate=False)

    def action_copy_all(self) -> None:
        """Copy all log lines to system clipboard."""
        if not self._lines:
            return
        text = "\n".join(self._lines)
        import subprocess

        try:
            proc = subprocess.Popen(
                ["pbcopy"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(text.encode())
            self.notify("Logs copied to clipboard")
        except FileNotFoundError:
            try:
                proc = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                proc.communicate(text.encode())
                self.notify("Logs copied to clipboard")
            except FileNotFoundError:
                self.notify("No clipboard tool found", severity="warning")
