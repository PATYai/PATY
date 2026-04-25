"""Root layout: main row on top, input bar at the bottom.

Main row keeps the conversation transcript on the left and the avatar +
equalizer column on the right. The input bar's size is updated each paint
to track the typed buffer's wrapped height.
"""

from __future__ import annotations

from rich.layout import Layout


def build_layout() -> Layout:
    root = Layout(name="root")
    root.split_column(
        Layout(name="main"),
        Layout(name="input", size=3),
    )
    root["main"].split_row(
        Layout(name="transcript", ratio=2),
        Layout(name="side", ratio=1, minimum_size=24),
    )
    root["side"].split_column(
        Layout(name="avatar"),
        Layout(name="equalizer"),
    )
    return root
