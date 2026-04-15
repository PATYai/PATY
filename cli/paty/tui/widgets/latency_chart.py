"""Stacked horizontal bar chart showing avg/p95/max latency per pipeline stage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.style import Style
from rich.text import Text
from textual.widget import Widget

if TYPE_CHECKING:
    from paty.dashboard.provider import DashboardProvider
    from paty.dashboard.snapshot import DashboardSnapshot, StageMetrics

_STYLE_AVG = Style(color="rgb(80,200,80)")
_STYLE_P95 = Style(color="rgb(220,200,50)")
_STYLE_MAX = Style(color="rgb(220,80,80)")
_STYLE_EMPTY = Style(color="rgb(60,60,60)")
_STYLE_LABEL = Style(bold=True)
_STYLE_DIM = Style(dim=True)

_STAGES = [
    ("STT TTFB", "stt"),
    ("LLM TTFB", "llm_ttfb"),
    ("TTS TTFB", "tts"),
]


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.0f}ms"


def _render_bar(stage: StageMetrics, bar_width: int, scale: float) -> Text:
    """Render a single stacked bar: green(avg) + yellow(p95-avg) + red(max-p95)."""
    bar = Text()
    avg = stage.avg_ms or 0.0
    p95 = stage.p95_ms or 0.0
    max_v = stage.max_ms or 0.0

    if scale <= 0:
        bar.append("░" * bar_width, _STYLE_EMPTY)
        return bar

    avg_chars = int((avg / scale) * bar_width)
    p95_chars = int((p95 / scale) * bar_width) - avg_chars
    max_chars = int((max_v / scale) * bar_width) - avg_chars - p95_chars
    remaining = bar_width - avg_chars - max(p95_chars, 0) - max(max_chars, 0)

    bar.append("█" * max(avg_chars, 0), _STYLE_AVG)
    bar.append("█" * max(p95_chars, 0), _STYLE_P95)
    bar.append("█" * max(max_chars, 0), _STYLE_MAX)
    bar.append("░" * max(remaining, 0), _STYLE_EMPTY)

    return bar


class LatencyChartWidget(Widget):
    """Stacked bar charts for STT/LLM/TTS latency with avg/p95/max segments."""

    DEFAULT_CSS = """
    LatencyChartWidget {
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(self, provider: DashboardProvider, **kwargs):
        super().__init__(**kwargs)
        self._provider = provider
        self._metrics_reader = None  # set by app once metrics are initialized
        self._snapshot: DashboardSnapshot | None = None

    def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh_metrics)

    def _refresh_metrics(self) -> None:
        self._snapshot = self._provider.snapshot(self._metrics_reader)
        self.refresh()

    def render(self) -> Text:
        lines: list[Text] = []

        # Title
        title = Text("Pipeline Latency", style="bold underline")
        lines.append(title)
        lines.append(Text())

        if self._snapshot is None:
            lines.append(Text("Waiting for metrics…", style="dim italic"))
            return Text("\n").join(lines)

        snap = self._snapshot

        # Determine auto-scale: max of all max values
        all_maxes = [getattr(snap, attr).max_ms or 0.0 for _, attr in _STAGES]
        scale = max(all_maxes) * 1.1 if any(m > 0 for m in all_maxes) else 100.0

        label_width = 10
        bar_width = max(self.size.width - label_width - 30, 10)

        for display_name, attr in _STAGES:
            stage: StageMetrics = getattr(snap, attr)

            line = Text()
            line.append(f"{display_name:<{label_width}}", _STYLE_LABEL)
            line.append_text(_render_bar(stage, bar_width, scale))
            line.append(
                f"  {_fmt_ms(stage.avg_ms):>6} / "
                f"{_fmt_ms(stage.p95_ms):>6} / "
                f"{_fmt_ms(stage.max_ms):>6}",
                _STYLE_DIM,
            )
            lines.append(line)
            lines.append(Text())  # spacing between bars

        # Legend
        legend = Text()
        legend.append("  ■", _STYLE_AVG)
        legend.append(" avg  ", _STYLE_DIM)
        legend.append("■", _STYLE_P95)
        legend.append(" p95  ", _STYLE_DIM)
        legend.append("■", _STYLE_MAX)
        legend.append(" max", _STYLE_DIM)
        lines.append(legend)

        # Counters
        lines.append(Text())
        lines.append(Text())
        tokens_line = Text()
        tokens_line.append("Tokens  ", _STYLE_LABEL)
        tokens_line.append(
            f"{snap.llm_tokens_prompt:,} prompt / "
            f"{snap.llm_tokens_completion:,} completion",
            _STYLE_DIM,
        )
        lines.append(tokens_line)

        chars_line = Text()
        chars_line.append("TTS     ", _STYLE_LABEL)
        chars_line.append(f"{snap.tts_characters:,} characters", _STYLE_DIM)
        lines.append(chars_line)

        return Text("\n").join(lines)
