"""Equalizer — bar display driven by audio frame levels from the bus."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from rich.console import Console, ConsoleOptions, RenderResult
from rich.panel import Panel
from rich.text import Text

from paty.tui.theme import Theme

# 8ths of a cell, bottom→top: " " is empty, "█" is full.
_BLOCKS = " ▁▂▃▄▅▆▇█"
EQ_CHANNELS = 16
# Per-frame multiplicative decay applied to old bar values; new value is
# `max(new, old * decay)` so bars hang on between syllables.
_DECAY = 0.85
# Magnitude scaling. FFT magnitudes from PCM16 normalized to [-1, 1] sit
# well below 1.0; this gain plus the sqrt curve below gives full bars on
# loud speech without clipping on peaks.
_GAIN = 7.0
# Floor for the log-spaced frequency edges; below this is mostly mic
# rumble / DC drift and would just make the lowest band sit lit.
_F_MIN_HZ = 60.0
# Visual headroom: a level=1.0 bar fills (1 - _HEADROOM) of the panel
# height so peaks don't read as clipping/peaking against the top border.
_HEADROOM = 0.25


def compute_levels(pcm: bytes, sample_rate: int, prev: list[float]) -> list[float]:
    """Bucket a PCM16LE frame into log-spaced FFT bands; peak-decay-smooth.

    Returns a fresh list so callers can swap it in atomically.
    """
    if len(pcm) < EQ_CHANNELS * 4 or sample_rate <= 0:
        return [v * _DECAY for v in prev]
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    n = samples.size
    if n < EQ_CHANNELS * 2:
        return [v * _DECAY for v in prev]
    mag = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)
    edges = np.logspace(
        np.log10(_F_MIN_HZ), np.log10(sample_rate / 2.0), EQ_CHANNELS + 1
    )
    sums, _ = np.histogram(freqs, bins=edges, weights=mag)
    counts, _ = np.histogram(freqs, bins=edges)
    buckets = sums / np.maximum(counts, 1)
    buckets = np.sqrt(buckets / np.sqrt(n) * _GAIN)
    buckets = np.minimum(1.0, buckets)
    return [max(float(b), p * _DECAY) for b, p in zip(buckets, prev, strict=True)]


def _row_style(row_from_bottom: int, height: int, theme: Theme) -> str:
    if height <= 1:
        return theme.equalizer_low
    # Style relative to the effective bar range (the part of the panel
    # peaks can actually reach), so the gradient lands on visible bar
    # heights instead of decorating empty headroom rows.
    effective = max(1.0, height * (1.0 - _HEADROOM))
    rel = row_from_bottom / effective
    if rel < 0.50:
        return theme.equalizer_low
    if rel < 0.85:
        return theme.equalizer_mid
    return theme.equalizer_high


def _cell_char(level: float, row_from_bottom: int, height: int) -> str:
    bar_h = max(0.0, min(1.0, level)) * height * (1.0 - _HEADROOM)
    fill = bar_h - row_from_bottom
    if fill <= 0:
        return " "
    if fill >= 1:
        return "█"
    return _BLOCKS[max(1, min(8, round(fill * 8)))]


class _EqRenderable:
    """Multi-row, gradient-colored bars sized to the cell's allotted height."""

    def __init__(self, theme: Theme, levels: list[float]) -> None:
        self.theme = theme
        self.levels = levels

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        height = max(1, options.max_height or 4)
        width = max(1, options.max_width or len(self.levels))
        # Spread `width` columns across len(self.levels) bands so the band
        # widths sum to exactly `width`. Some bands are 1 col wider than
        # others when width isn't a clean multiple — that distributes the
        # leftover evenly instead of piling it on one side.
        n = len(self.levels)
        edges = [round(i * width / n) for i in range(n + 1)]
        band_widths = [edges[i + 1] - edges[i] for i in range(n)]
        for top_idx in range(height):
            row_from_bottom = height - 1 - top_idx
            line = Text(
                style=_row_style(row_from_bottom, height, self.theme),
                no_wrap=True,
            )
            for lvl, w in zip(self.levels, band_widths, strict=True):
                if w <= 0:
                    continue
                line.append(_cell_char(lvl, row_from_bottom, height) * w)
            yield line


def render_equalizer(theme: Theme, levels: Iterable[float] | None = None) -> Panel:
    if not levels:
        levels = [0.0] * EQ_CHANNELS
    return Panel(
        _EqRenderable(theme, list(levels)),
        title="equalizer",
        border_style=theme.border,
    )
