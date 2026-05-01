"""PATY CLI — declarative voice agent deployment on Pipecat."""

from __future__ import annotations

import asyncio
from importlib import resources

import click
from rich.console import Console
from rich.table import Table

from paty import __version__

console = Console()


def detect_installed_backend() -> str | None:
    for name, module in [("mlx", "mlx_lm"), ("llama", "llama_cpp")]:
        try:
            __import__(module)
            return name
        except ImportError:
            continue
    return None


def _bundled_default_config() -> str:
    """Return the filesystem path to the default config bundled with paty."""
    return str(resources.files("paty.examples").joinpath("paty.yaml"))


@click.group()
@click.version_option(version=__version__)
def cli():
    """PATY — Declarative voice agent deployment on Pipecat."""


@cli.command()
@click.argument("config", type=click.Path(exists=True), required=False)
def run(config: str | None):
    """Start the voice agent.

    With no CONFIG, runs the bundled default (examples/paty.yaml).
    """
    if detect_installed_backend() is None:
        click.echo("No backend installed.\n")
        click.echo("  uv tool install 'paty[mlx]'   # Apple Silicon")
        click.echo("  uv tool install 'paty[cuda]'  # NVIDIA GPU")
        click.echo("  uv tool install 'paty[cpu]'   # Fallback")
        raise SystemExit(1)
    asyncio.run(_run(config or _bundled_default_config()))


async def _run(config_path: str) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from paty.bus import BusAction, BusCommand, BusObserver, WebSocketBus
    from paty.bus.events import EventType, InputMuted, SessionEnded, SessionStarted
    from paty.config.loader import load_config
    from paty.config.schema import Platform
    from paty.hardware.detect import detect_hardware, wire_memory
    from paty.hardware.profiles import resolve_profile
    from paty.metrics.setup import setup_metrics
    from paty.pak.runtime import (
        apply_pak_voice,
        resolve_persona,
        warn_if_llm_pin_off_profile,
    )
    from paty.pipeline.builder import build_local_transport, build_pipeline
    from paty.pipeline.mute import InputMuteFilter
    from paty.pipeline.text_input import TextInputInjector
    from paty.resolve.resolver import resolve_services
    from paty.runtime.gpu_executor import create_gpu_executor
    from paty.runtime.manager import ManagedProcess, create_managed_llm
    from paty.tracing.setup import setup_tracing

    # 1. Load config + resolve persona (inline `pak.persona`, named PAK,
    #    or bundled default — see paty.pak.runtime.resolve_persona).
    raw_config = load_config(config_path)
    resolved_persona = resolve_persona(raw_config)
    raw_config = apply_pak_voice(raw_config, resolved_persona.pak)

    # 2. Initialize tracing
    tracer = setup_tracing(raw_config.tracing)

    # 3. Initialize metrics
    metrics_handle = setup_metrics(raw_config.metrics)

    managed: list[ManagedProcess] = []
    compute_executor: ThreadPoolExecutor | None = None
    bus: WebSocketBus | None = None

    try:
        with tracer.start_as_current_span("paty.startup") as startup_span:
            startup_span.set_attribute("paty.config_path", config_path)

            # 3. Detect hardware
            with tracer.start_as_current_span("paty.hardware.detect") as hw_span:
                hardware = detect_hardware()
                hw_span.set_attribute("paty.platform", hardware.platform.value)
                hw_span.set_attribute("paty.memory_mb", hardware.memory_mb)
                hw_span.set_attribute("paty.gpu", hardware.gpu_name or "none")

            console.print(
                f"[bold]Platform:[/] {hardware.platform.value}  "
                f"[bold]Memory:[/] {hardware.memory_mb}MB"
            )

            # 4. Resolve profile
            with tracer.start_as_current_span("paty.resolve.profile") as prof_span:
                profile = resolve_profile(raw_config.hardware, hardware)
                prof_span.set_attribute("paty.profile", profile.name)

            console.print(f"[bold]Profile:[/] {profile.name}")

            pak = resolved_persona.pak
            console.print(f"[bold]PAK:[/] {pak.name} v{pak.manifest.pak.version}")
            warn_msg = warn_if_llm_pin_off_profile(pak, profile.llm_model)
            if warn_msg:
                console.print(f"[yellow]warning:[/] {warn_msg}")

            # 5. Start managed LLM server
            llm_model = raw_config.pipeline.llm.model or profile.llm_model
            with tracer.start_as_current_span("paty.runtime.llm") as llm_span:
                llm = create_managed_llm(
                    llm_model, hardware.platform.value, profile=profile
                )
                console.print(f"[bold]LLM:[/] starting {llm.model_id}...")
                port = await llm.process.start()
                managed.append(llm.process)
                llm_span.set_attribute("paty.llm.port", port)
                llm_span.set_attribute("paty.llm.model_id", llm.model_id)

                # Warmup: force model into memory so first query is fast
                console.print("[bold]LLM:[/] warming up...")
                await llm.process.warmup(llm.model_id)

            # Point LLM config at the managed server
            raw_config.pipeline.llm = raw_config.pipeline.llm.model_copy(
                update={
                    "base_url": f"http://127.0.0.1:{port}/v1",
                    "model": llm.model_id,
                }
            )
            console.print(f"[bold]LLM:[/] ready on port {port}")

            # 6. Resolve services (STT + TTS in-process, LLM via managed server)
            # On MLX, a shared single-worker executor serializes every Metal
            # op across STT and TTS. Without this, two OS threads race on the
            # command queue and Metal asserts out.
            if hardware.platform == Platform.MLX:
                compute_executor = create_gpu_executor()
            with tracer.start_as_current_span("paty.resolve.services") as svc_span:
                services = resolve_services(
                    raw_config.pipeline,
                    hardware.platform,
                    profile,
                    compute_executor=compute_executor,
                )
                svc_span.set_attribute("paty.stt_class", type(services.stt).__name__)
                svc_span.set_attribute("paty.llm_class", type(services.llm).__name__)
                svc_span.set_attribute("paty.tts_class", type(services.tts).__name__)

            console.print(
                f"[bold]STT:[/] {type(services.stt).__name__}  "
                f"[bold]TTS:[/] {type(services.tts).__name__}"
            )

            # 6b. Wire in-process model memory to prevent paging
            wired = wire_memory(hardware, wire_fraction=profile.wire_fraction)
            if wired:
                console.print(
                    f"[bold]Memory:[/] wired {wired // (1024 * 1024)}MB to prevent swap"
                )

            # 7. Start the event bus (optional, TUI subscribes here)
            observers = [metrics_handle.observer]
            input_mute = InputMuteFilter()
            text_injector = TextInputInjector()
            if raw_config.bus.enabled:
                with tracer.start_as_current_span("paty.bus.start") as bus_span:
                    bus = WebSocketBus(
                        host=raw_config.bus.host, port=raw_config.bus.port
                    )
                    await bus.start()
                    bus_span.set_attribute("paty.bus.host", raw_config.bus.host)
                    bus_span.set_attribute("paty.bus.port", raw_config.bus.port)
                observers.append(BusObserver(bus))

                async def _handle_command(
                    cmd: BusCommand, _bus: WebSocketBus = bus
                ) -> None:
                    if cmd.action == BusAction.MUTE_TOGGLE:
                        new = await input_mute.toggle()
                    elif cmd.action == BusAction.MUTE_SET:
                        new = await input_mute.set_mute(bool(cmd.muted))
                    elif cmd.action == BusAction.CHAT_SEND:
                        await text_injector.inject(cmd.text or "")
                        return
                    else:
                        return
                    _bus.publish(EventType.INPUT_MUTED, InputMuted(muted=new))

                bus.on_command(_handle_command)
                console.print(
                    f"[bold]Bus:[/] ws://{raw_config.bus.host}:{raw_config.bus.port}"
                )

            # 8. Build pipeline with local audio transport
            with tracer.start_as_current_span("paty.pipeline.build"):
                transport = build_local_transport()
                _pipeline, task, runner = build_pipeline(
                    stt=services.stt,
                    llm=services.llm,
                    tts=services.tts,
                    transport=transport,
                    persona=resolved_persona.persona,
                    observers=observers,
                    input_mute_filter=input_mute,
                    text_injector=text_injector,
                )

        if bus is not None:
            avatar = resolved_persona.pak.avatar or None
            bus.publish(
                EventType.SESSION_STARTED,
                SessionStarted(
                    persona=resolved_persona.persona,
                    profile=profile.name,
                    platform=hardware.platform.value,
                    stt=type(services.stt).__name__,
                    llm=type(services.llm).__name__,
                    tts=type(services.tts).__name__,
                    avatar=avatar,
                ),
            )

        console.print(
            f"\n[green]Agent '{resolved_persona.pak.name}' running. "
            f"Speak into your mic.[/]"
        )
        console.print("[dim]Press Ctrl+C to stop.[/]\n")

        # 9. Run — blocks until cancelled
        await runner.run(task)

    finally:
        if bus is not None:
            bus.publish(EventType.SESSION_ENDED, SessionEnded(reason="shutdown"))
            await bus.stop()
        for proc in managed:
            await proc.stop()
        if compute_executor is not None:
            compute_executor.shutdown(wait=False)


@cli.command()
@click.argument("config", type=click.Path(exists=True))
@click.option("--output", "-o", default="bot.py", help="Output Python file path")
def eject(config: str, output: str):
    """Generate a standalone bot.py with no PATY dependency."""
    console.print("[yellow]Coming soon.[/]")


@cli.command()
def init():
    """Scaffold a starter paty.yaml and directory structure."""
    console.print("[yellow]Coming soon.[/]")


@cli.command()
def doctor():
    """Check that all dependencies are available and configured."""
    console.print("[yellow]Coming soon.[/]")


@cli.group()
def bus():
    """Inspect and interact with the PATY event bus."""


@bus.command("tail")
@click.option(
    "--url",
    default="ws://127.0.0.1:8765",
    show_default=True,
    help="WebSocket URL of a running PATY bus.",
)
@click.option(
    "--no-audio",
    is_flag=True,
    help="Suppress audio frame lines (control events only).",
)
def bus_tail(url: str, no_audio: bool):
    """Subscribe to a running bus and print events as they arrive."""
    from paty.bus.tail import run as run_tail

    run_tail(url, show_audio=not no_audio)


@bus.command("tui")
@click.option(
    "--url",
    default="ws://127.0.0.1:8765",
    show_default=True,
    help="WebSocket URL of a running PATY bus.",
)
def bus_tui(url: str):
    """Live conversation view subscribed to a running bus."""
    from paty.tui import run as run_tui

    run_tui(url)


@cli.command()
def profiles():
    """List available hardware profiles and their model selections."""
    from paty.hardware.profiles import PROFILES

    table = Table(title="Hardware Profiles")
    table.add_column("Profile", style="bold")
    table.add_column("STT Model")
    table.add_column("LLM Model")
    table.add_column("TTS")
    table.add_column("Voice")

    for _key, p in PROFILES.items():
        table.add_row(p.name, p.stt_model, p.llm_model, p.tts_provider, p.tts_voice)

    console.print(table)


@cli.group()
def pak():
    """Manage PATY PAKs (Personality Augmentation Kits)."""


@pak.command("list")
def pak_list():
    """List installed PAKs (user-installed and bundled)."""
    from paty.pak.loader import PakLoadError
    from paty.pak.registry import PakRegistry

    reg = PakRegistry()
    active = reg.active_name()

    table = Table(title="Installed PAKs")
    table.add_column("Name", style="bold")
    table.add_column("Version")
    table.add_column("Description")
    table.add_column("Active")

    names = reg.list()
    if not names:
        console.print("[yellow]No PAKs found.[/]")
        return

    for name in names:
        try:
            loaded = reg.get(name)
            table.add_row(
                name,
                loaded.manifest.pak.version,
                loaded.manifest.pak.description,
                "✓" if name == active else "",
            )
        except PakLoadError as e:
            table.add_row(name, "[red]invalid[/]", str(e), "")

    console.print(table)


@pak.command("active")
def pak_active():
    """Print the active PAK name."""
    from paty.pak.registry import PakRegistry

    reg = PakRegistry()
    name = reg.active_name()
    if name is None:
        console.print(
            "[dim]No PAK selected. The bundled 'paty' PAK will be used at runtime.[/]"
        )
    else:
        console.print(name)


@pak.command("validate")
@click.argument("path", type=click.Path(exists=True))
def pak_validate(path: str):
    """Validate a PAK directory."""
    from paty.pak.loader import PakLoadError, load_pak

    try:
        loaded = load_pak(path)
    except PakLoadError as e:
        console.print(f"[red]Invalid PAK:[/] {e}")
        raise click.exceptions.Exit(1) from None

    meta = loaded.manifest.pak
    voice = loaded.manifest.voice
    console.print(f"[green]✓[/] {loaded.name} (v{meta.version})")
    if meta.description:
        console.print(f"  description: {meta.description}")
    console.print(
        f"  tts: {voice.tts.provider}/{voice.tts.voice or '<profile default>'}"
    )
    if voice.llm.model:
        console.print(f"  llm pin: {voice.llm.model}")


@pak.command("switch")
@click.argument("name")
def pak_switch(name: str):
    """Set the active PAK. Takes effect on the next ``paty run``."""
    from paty.pak.loader import PakLoadError
    from paty.pak.registry import PakRegistry

    reg = PakRegistry()
    try:
        reg.set_active(name)
    except PakLoadError as e:
        console.print(f"[red]Cannot switch:[/] {e}")
        raise click.exceptions.Exit(1) from None

    console.print(
        f"Active PAK set to [bold]{name}[/]. "
        "Hot-swap not yet implemented — restart `paty run` to apply."
    )
