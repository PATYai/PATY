"""Root layout: transcript on the left, avatar top-right, equalizer bottom-right."""

from __future__ import annotations

from rich.layout import Layout


def build_layout() -> Layout:
    root = Layout(name="root")
    root.split_row(
        Layout(name="transcript", ratio=2),
        Layout(name="side", ratio=1, minimum_size=24),
    )
    root["side"].split_column(
        Layout(name="avatar"),
        Layout(name="equalizer"),
    )
    return root
