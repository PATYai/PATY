"""Textual TUI application for the PATY voice agent dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header

from paty.dashboard.provider import DashboardProvider
from paty.tui.widgets.equalizer import EqualizerWidget
from paty.tui.widgets.latency_chart import LatencyChartWidget
from paty.tui.widgets.logo import LogoWidget
from paty.tui.widgets.logs import LogsWidget


def _patch_for_textual() -> None:
    """Fix subprocess/multiprocessing under Textual's alternate screen.

    Textual replaces sys.stdout/stderr with wrappers whose .fileno()
    returns -1.  Two things break:

    1. subprocess.Popen with default (None) stdio inherits those -1 FDs.
    2. multiprocessing.resource_tracker._launch() calls
       sys.stderr.fileno(), gets -1, puts it in fds_to_pass, and
       _posixsubprocess.fork_exec rejects it.

    We fix both at the source: patch spawnv_passfds to filter out
    negative FDs, and patch Popen to default stdio to DEVNULL.
    """
    import multiprocessing.util

    # --- Fix 1: multiprocessing.util.spawnv_passfds ---
    _orig_spawnv = multiprocessing.util.spawnv_passfds

    def _safe_spawnv(path, args, passfds):
        # Filter out any negative FDs (e.g. -1 from Textual's stderr wrapper)
        passfds = [fd for fd in passfds if fd >= 0]
        return _orig_spawnv(path, args, passfds)

    multiprocessing.util.spawnv_passfds = _safe_spawnv

    # --- Fix 2: subprocess.Popen default stdio ---
    orig_popen_init = subprocess.Popen.__init__

    def _safe_popen_init(self, *args, **kwargs):
        devnull = subprocess.DEVNULL
        for key in ("stdin", "stdout", "stderr"):
            if kwargs.get(key) is None:
                kwargs[key] = devnull
        kwargs.setdefault("close_fds", True)
        return orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _safe_popen_init  # type: ignore[method-assign]


class PatyApp(App):
    """Full-screen TUI dashboard for monitoring the PATY voice pipeline."""

    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "PATY"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "force_quit", "Quit", priority=True),
        Binding("escape", "force_quit", "Quit", priority=True),
    ]

    def __init__(self, config_path: str, **kwargs):
        super().__init__(**kwargs)
        self._config_path = config_path
        self._provider = DashboardProvider()
        self._pipeline_task: asyncio.Task | None = None
        self._managed: list = []
        self._metrics_handle = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left-panel"):
                yield LogoWidget()
                yield EqualizerWidget(self._provider)
            with Vertical(id="right-panel"):
                yield LatencyChartWidget(self._provider)
                yield LogsWidget(id="logs")
        yield Footer()

    @property
    def logs(self) -> LogsWidget:
        return self.query_one("#logs", LogsWidget)

    def _log(self, message: str, level: str = "info") -> None:
        """Write a message to the logs panel."""
        with contextlib.suppress(Exception):
            self.logs.log_message(message, level=level)

    async def on_mount(self) -> None:
        _patch_for_textual()
        self._pipeline_task = asyncio.create_task(self._run_pipeline())

    async def _run_pipeline(self) -> None:
        """Start the voice pipeline, mirroring cli._run() with TUI hooks."""
        try:
            from loguru import logger

            from paty.config.loader import load_config
            from paty.hardware.detect import detect_hardware, wire_memory
            from paty.hardware.profiles import resolve_profile
            from paty.metrics.setup import setup_metrics
            from paty.pipeline.builder import build_local_transport, build_pipeline
            from paty.resolve.resolver import resolve_services
            from paty.runtime.manager import create_managed_llm
            from paty.tracing.setup import setup_tracing

            # Redirect loguru to the TUI logs panel instead of stderr
            _level_map = {
                "DEBUG": "info",
                "INFO": "info",
                "SUCCESS": "success",
                "WARNING": "warning",
                "ERROR": "error",
                "CRITICAL": "error",
            }

            def _loguru_sink(message):
                level_name = message.record["level"].name
                tui_level = _level_map.get(level_name, "info")
                self._log(str(message).rstrip(), level=tui_level)

            logger.remove()
            logger.add(
                _loguru_sink,
                format="{time:HH:mm:ss} | {level:<7} | {message}",
                level="INFO",
            )

            raw_config = load_config(self._config_path)
            setup_tracing(raw_config.tracing)

            # Disable the Rich console exporter — we show metrics in the TUI
            raw_config.metrics.console_interval = 0

            # Wire the dashboard collector into the metrics observer
            metrics_handle = setup_metrics(
                raw_config.metrics, collector=self._provider.collector
            )
            self._metrics_handle = metrics_handle

            # Point the latency chart at the OTEL reader for counter data
            self.query_one(
                LatencyChartWidget
            )._metrics_reader = metrics_handle.in_memory_reader

            hardware = detect_hardware()
            profile = resolve_profile(raw_config.hardware, hardware)

            self._log(
                f"Platform: {hardware.platform.value}  "
                f"Memory: {hardware.memory_mb}MB  "
                f"Profile: {profile.name}"
            )

            # Start managed LLM server
            llm_model = raw_config.pipeline.llm.model or profile.llm_model
            llm = create_managed_llm(
                llm_model, hardware.platform.value, profile=profile
            )
            self._log(f"LLM: starting {llm.model_id}...")
            port = await llm.process.start()
            self._managed.append(llm.process)

            self._log("LLM: warming up...")
            await llm.process.warmup(llm.model_id)

            raw_config.pipeline.llm = raw_config.pipeline.llm.model_copy(
                update={
                    "base_url": f"http://127.0.0.1:{port}/v1",
                    "model": llm.model_id,
                }
            )
            self._log(f"LLM: ready on port {port}", level="success")

            services = resolve_services(raw_config.pipeline, hardware.platform, profile)

            self._log(
                f"STT: {type(services.stt).__name__}  "
                f"TTS: {type(services.tts).__name__}"
            )

            wire_memory(hardware, wire_fraction=profile.wire_fraction)

            transport = build_local_transport()
            _pipeline, task, runner = build_pipeline(
                stt=services.stt,
                llm=services.llm,
                tts=services.tts,
                transport=transport,
                persona=raw_config.agent.persona,
                observers=[],
            )

            # Add observers after build so they're registered when
            # TaskObserver.start() runs inside runner.run().
            task.add_observer(metrics_handle.observer)

            self._log("Pipeline running - speak into your mic", level="success")
            await runner.run(task)

        except asyncio.CancelledError:
            pass
        except Exception:
            import traceback

            tb = traceback.format_exc()
            with open("/tmp/paty-tui-crash.log", "w") as f:
                f.write(tb)
            self._log(tb, level="error")
        finally:
            for proc in self._managed:
                await proc.stop()

    async def action_force_quit(self) -> None:
        """Stop managed processes, then exit."""
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        # Kill managed LLM servers so they don't outlive us
        for proc in self._managed:
            try:
                await asyncio.wait_for(proc.stop(), timeout=3.0)
            except (TimeoutError, Exception):
                if proc.process and proc.process.poll() is None:
                    proc.process.kill()
        self.exit()
