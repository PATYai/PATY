"""Spawn ``paty run``, drive the boot screen, hand off to ``paty bus tui``.

Process lifecycle only — no Rich, no UI. Communicates with the boot screen
through :meth:`BootScreen.write_line` and with the child via a one-byte
ready pipe (passed as ``--ready-fd``).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from paty.startup.boot_screen import BootScreen

_DEFAULT_BUS_URL = "ws://127.0.0.1:8765"


def _resolve_bus_url() -> str | None:
    """Return the WS URL of the bus the child will start.

    Returns ``None`` if the bus is disabled in config — the caller should
    fail fast since the TUI has nothing to attach to.
    """
    try:
        from paty.cli import _bundled_default_config
        from paty.config.loader import load_config

        cfg = load_config(_bundled_default_config())
    except Exception:
        return _DEFAULT_BUS_URL
    if not cfg.bus.enabled:
        return None
    return f"ws://{cfg.bus.host}:{cfg.bus.port}"


def _open_log_file() -> tuple[Path, "object"]:
    log_dir = Path.home() / ".paty" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"run-{int(time.time())}.log"
    return path, path.open("w", buffering=1)


def _kill_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def launch() -> None:
    bus_url = _resolve_bus_url()
    if bus_url is None:
        sys.stderr.write(
            "paty: bus is disabled in config; the boot+TUI flow needs "
            "`bus.enabled: true`.\n"
            "Either enable the bus in your paty.yaml, or run `paty run` "
            "directly.\n"
        )
        raise SystemExit(2)

    ready_r, ready_w = os.pipe()
    log_path, log_file = _open_log_file()

    env = {**os.environ, "FORCE_COLOR": "1"}

    proc = subprocess.Popen(
        [sys.executable, "-m", "paty", "run", "--ready-fd", str(ready_w)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        env=env,
        pass_fds=(ready_w,),
        start_new_session=True,
    )
    os.close(ready_w)

    boot = BootScreen()
    boot.start()

    ready_event = threading.Event()

    def _watch_ready() -> None:
        try:
            data = os.read(ready_r, 1)
        except OSError:
            data = b""
        finally:
            try:
                os.close(ready_r)
            except OSError:
                pass
        if data:
            ready_event.set()

    def _pump_logs() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                log_file.write(line)
                if not ready_event.is_set():
                    boot.write_line(line)
        finally:
            try:
                log_file.close()
            except OSError:
                pass

    watcher = threading.Thread(target=_watch_ready, daemon=True)
    pump = threading.Thread(target=_pump_logs, daemon=True)
    watcher.start()
    pump.start()

    try:
        while not ready_event.is_set():
            if proc.poll() is not None:
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        boot.stop()
        _kill_group(proc.pid, signal.SIGINT)
        proc.wait()
        pump.join(timeout=2)
        raise SystemExit(130) from None

    if not ready_event.is_set():
        # Child exited before signaling ready — surface its captured output.
        boot.stop()
        proc.wait()
        pump.join(timeout=2)
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        try:
            sys.stdout.write(log_path.read_text())
        except OSError:
            pass
        sys.stderr.write(
            f"\npaty: startup failed (exit {proc.returncode}). "
            f"Logs saved to {log_path}\n"
        )
        raise SystemExit(proc.returncode or 1)

    # Ready — tear down the boot screen and hand off to the TUI.
    boot.stop()
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()

    try:
        from paty.tui import run as run_tui

        run_tui(bus_url)
    finally:
        _kill_group(proc.pid, signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill_group(proc.pid, signal.SIGTERM)
            proc.wait()
        pump.join(timeout=2)
        sys.stderr.write(f"\npaty: full startup logs saved to {log_path}\n")
