"""Real-time audio equalizer widget with blue/green gradient."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.widget import Widget

if TYPE_CHECKING:
    from paty.dashboard.provider import DashboardProvider

# Block characters from full to empty (8 levels)
_BLOCKS = "█▇▆▅▄▃▂▁"

# Blue-to-green gradient (bottom to top, 16 steps)
_GRADIENT = [
    Color.from_rgb(20, 60, 160),
    Color.from_rgb(20, 75, 170),
    Color.from_rgb(15, 90, 175),
    Color.from_rgb(10, 105, 175),
    Color.from_rgb(5, 120, 170),
    Color.from_rgb(0, 135, 165),
    Color.from_rgb(0, 150, 155),
    Color.from_rgb(0, 160, 145),
    Color.from_rgb(0, 170, 130),
    Color.from_rgb(0, 180, 115),
    Color.from_rgb(0, 195, 100),
    Color.from_rgb(0, 210, 90),
    Color.from_rgb(0, 220, 80),
    Color.from_rgb(0, 235, 70),
    Color.from_rgb(0, 245, 60),
    Color.from_rgb(0, 255, 50),
]

_BAND_LABELS = ["SUB", "BAS", "LOW", "MID", "UPR", "PRS", "BRI", "AIR"]


class EqualizerWidget(Widget):
    """8-band audio equalizer with vertical bars and blue/green gradient."""

    DEFAULT_CSS = """
    EqualizerWidget {
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(self, provider: DashboardProvider, **kwargs):
        super().__init__(**kwargs)
        self._provider = provider
        self._bands: list[float] = [0.0] * 8

    def on_mount(self) -> None:
        self.set_interval(1 / 12, self._refresh_levels)

    def _refresh_levels(self) -> None:
        snapshot = self._provider.snapshot()
        self._bands = snapshot.audio.bands
        self.refresh()

    def render(self) -> Text:
        height = max(self.size.height - 3, 4)  # leave room for labels + padding
        bar_width = 3
        gap = 1
        num_bands = min(len(self._bands), 8)

        lines: list[Text] = []

        # Build rows top-down
        for row in range(height):
            line = Text()
            threshold = 1.0 - (row / height)

            for band_idx in range(num_bands):
                level = self._bands[band_idx]
                gradient_idx = min(
                    int((1.0 - row / height) * (len(_GRADIENT) - 1)),
                    len(_GRADIENT) - 1,
                )
                color = _GRADIENT[gradient_idx]
                style = Style(color=color)

                if level >= threshold:
                    line.append("█" * bar_width, style=style)
                elif level >= threshold - (1.0 / height):
                    # Partial block for the transition row
                    frac = (level - (threshold - 1.0 / height)) * height
                    block_idx = max(
                        0, min(len(_BLOCKS) - 1, int((1.0 - frac) * len(_BLOCKS)))
                    )
                    line.append(_BLOCKS[block_idx] * bar_width, style=style)
                else:
                    line.append(" " * bar_width)

                if band_idx < num_bands - 1:
                    line.append(" " * gap)

            lines.append(line)

        # Label row
        label_line = Text()
        for i, label in enumerate(_BAND_LABELS[:num_bands]):
            label_line.append(f"{label:^{bar_width}}", style="dim")
            if i < num_bands - 1:
                label_line.append(" " * gap)
        lines.append(label_line)

        return Text("\n").join(lines)
