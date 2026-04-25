# PATY — Please & Thank You

Declarative voice agent deployment on Pipecat. Write a YAML config, run `paty run config.yaml`, get a working voice agent. No `bot.py` to write.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — the Python package manager used to install and run PATY. Install with:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Platform-specific toolchain** for local inference:
  - **Apple Silicon (macOS arm64):** nothing extra — the `[mlx]` extra pulls in MLX.
  - **NVIDIA GPU (CUDA):** a working CUDA toolchain so `llama-cpp-python` can build with GPU offload. See the [llama-cpp-python CUDA build docs](https://llama-cpp-python.readthedocs.io/en/latest/#installation-with-specific-hardware-acceleration-blas-cuda-metal-etc).
  - **CPU-only:** a C/C++ toolchain (`build-essential` on Linux, Xcode Command Line Tools on macOS) for `llama-cpp-python`.

## Installation

```bash
git clone https://github.com/PATYai/PATY.git
cd PATY/cli
```

Pick the extra that matches your hardware and sync:

```bash
# Apple Silicon (M1/M2/M3/M4)
uv sync --extra mlx

# NVIDIA GPU
uv sync --extra cuda

# CPU-only fallback
uv sync --extra cpu
```

The extras install Pipecat plus the local inference backend (MLX or `llama-cpp-python`). Skip them only if you plan to point PATY at remote services.

### External services

- **LLM** — PATY spawns a managed inference server automatically (`mlx_lm.server` on Apple Silicon, `llama_cpp.server` on CUDA/CPU). No separate Ollama install is required; models are pulled from Hugging Face on first run.
- **TTS on CUDA/CPU** — the `kokoro` provider expects an OpenAI-compatible Kokoro FastAPI server at `http://localhost:8880/v1`. The easiest way is the Docker image from [remsky/Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI). Apple Silicon runs Kokoro in-process via `mlx-audio` and needs nothing extra.
- **Piper (CPU alternative)** — `tts: piper` downloads its voice model on first use; no server needed.

## First run

```bash
uv run paty run examples/paty.yaml
```

On first launch PATY will:

1. Detect your platform and memory, then pick a hardware profile.
2. Download the LLM weights (a few GB — the first start is slow; subsequent runs hit the Hugging Face cache).
3. Download the Whisper STT model on first use.
4. Start the managed LLM server, warm it up, then open a local mic/speaker transport so you can talk to the agent.

Press `Ctrl+C` to stop.

## Development install

```bash
uv sync --extra mlx --extra dev          # or --extra cuda / --extra cpu
uv run pytest tests/ -v                  # run tests
uv run ruff check paty/ tests/           # lint
uv run ruff format --check paty/ tests/  # format check
```

## Config

The YAML config is PATY's primary interface. A minimal example:

```yaml
agent:
  name: front-desk
  persona: "You are a receptionist for Dr. Smith's dental office."

pipeline:
  stt: whisper
  llm: ollama
  tts: kokoro
  vad: silero

hardware:
  profile: auto    # or: apple-16gb, apple-24gb, cuda-24gb, cpu-only

sip:
  provider: voip-ms
  host: sip.voip.ms
  username: "100000"
  password: "${SIP_PASSWORD}"
  did: "+13035551234"

tracing:
  enabled: true
  console: true
```

Pipeline entries accept string shorthand (`stt: whisper`) or expanded form:

```yaml
pipeline:
  stt:
    provider: whisper
    model: large-v3-turbo
  llm:
    provider: ollama
    model: qwen3:14b
    base_url: http://localhost:11434/v1
  tts:
    provider: kokoro
    voice: af_bella
    base_url: http://localhost:8880/v1
```

Environment variables in `${VAR}` syntax are interpolated at load time.

## CLI Commands

```
paty run <config.yaml>       Start the voice agent
paty bus tail                Subscribe to a running bus and print events
paty bus tui                 Live conversation view subscribed to the bus
paty profiles                List hardware profiles and their model selections
paty init                    Scaffold a starter config (coming soon)
paty doctor                  Check dependencies (coming soon)
paty eject <config.yaml>     Generate standalone bot.py (coming soon)
```

## Event Bus

PATY can publish session events over a WebSocket so other processes (e.g. a TUI) can observe what the pipeline is doing without being coupled to it. Enable it in the config:

```yaml
bus:
  enabled: true            # publish session events for subscribers
  host: 127.0.0.1
  port: 8765
```

With the bus enabled, `paty run` starts a local WebSocket server at `ws://host:port`. Subscribers receive two frame types:

- **Text frames** — JSON control events with envelope `{v, seq, ts_ms, session_id, type, data}`. Types cover session lifecycle (`session.started`, `session.ended`), user turn (`user.speech_started/stopped`, `user.transcript.partial/final`), agent turn (`agent.thinking_started`, `agent.response.delta/completed`, `agent.speech_started/stopped`), derived `state.changed` (idle/listening/thinking/speaking), `metrics.tick`, `input.muted`, and `error`/`log`.
- **Binary frames** — a 16-byte header followed by PCM16LE audio samples. Header: `magic(1)`, `version(1)`, `stream(1: 1=mic, 2=agent)`, `reserved(1)`, `sample_rate(u16 LE)`, `channels(u16 LE)`, `seq(u32 LE)`, `ts_ms(u32 LE)` since session start.

The server fans out to any number of subscribers; control events never drop (overflow disconnects the slow subscriber), audio frames drop-oldest under backpressure.

### Bus actions

Subscribers can also send JSON commands to the bus to control the agent. Each command is a single JSON object:

```json
{"action": "mute.toggle"}
{"action": "mute.set", "muted": true}
```

| Action | Payload | Effect |
|--------|---------|--------|
| `mute.toggle` | — | Flip the mic mute. While muted, mic audio is dropped before reaching STT, so PATY can't hear you. |
| `mute.set` | `muted: bool` | Set the mute to an explicit state. |

Every state change is broadcast back as an `input.muted` event with `{muted: bool}` so all subscribers stay in sync.

### `paty bus tail`

Connects to a running bus and pretty-prints events as they arrive. Useful for verifying the bus end-to-end and as a reference implementation for TUI subscribers.

```bash
# terminal 1 — run the agent with bus.enabled: true
uv run paty run examples/paty.yaml

# terminal 2 — tail the bus
uv run paty bus tail                           # defaults to ws://127.0.0.1:8765
uv run paty bus tail --url ws://remote:8765    # different host/port
uv run paty bus tail --no-audio                # hide audio frame lines
```

### `paty bus tui`

Full-screen view of the same stream — transcript on the left, avatar top-right, equalizer bottom-right.

```bash
uv run paty bus tui                            # defaults to ws://127.0.0.1:8765
uv run paty bus tui --url ws://remote:8765
```

Built on Rich's immediate-mode `Live`: hold state in memory, rebuild the renderable tree on each event, let the library diff and repaint. `Layout` carves the terminal into named regions and each widget is a pure `(state) -> Renderable` function, so swapping a stub for real content is a one-file edit.

```
paty/tui/
├── __init__.py            — exports run
├── app.py                 — event loop, UIState, repaint
├── conversation.py        — Conversation/Turn
├── layout.py              — root split tree
└── widgets/
    ├── __init__.py
    ├── transcript.py      — conversation renderer
    ├── avatar.py          — stub face keyed off agent state
    └── equalizer.py       — stub bar chart (zero levels for now)
```

The avatar reacts to `state.changed` events out of the box (idle/listening/thinking/speaking). The equalizer is a visual stub — wiring it to real levels means subscribing to the bus's binary audio frames (`paty.bus.codec.unpack_audio_frame`) and computing per-band RMS.

## Hardware Profiles

When `profile: auto`, PATY detects your platform and memory to pick the best profile.

| Profile | STT | LLM | TTS | Memory Budget |
|---------|-----|-----|-----|---------------|
| apple-16gb | distil-whisper-large-v3 | qwen3:8b Q4 | kokoro | ~5.5GB |
| apple-24gb | large-v3-turbo | qwen3:14b Q4 | kokoro | ~9.5GB |
| cuda-24gb | distil-large-v2 | qwen3:14b Q4 | kokoro | ~9.5GB |
| cpu-only | distil-medium-en | qwen3:4b Q4 | piper | ~3GB |

## Architecture

PATY is a runtime resolver, not a code generator. It parses YAML, detects hardware, resolves config keys to Pipecat service constructors, builds a live Pipeline, and starts the runner.

```
YAML config
  → config loader (ruamel.yaml + Pydantic validation)
  → hardware detector (platform, GPU, memory)
  → service resolver (config keys → Pipecat service instances)
  → pipeline builder (services → Pipecat Pipeline)
  → runner (starts Pipecat PipelineRunner)
```

Every phase is traced via OpenTelemetry. Once the pipeline starts, Pipecat's built-in OTel tracing takes over for per-turn STT/LLM/TTS spans.

## Package Structure

```
paty/
├── cli.py                 # click CLI commands
├── config/
│   ├── schema.py          # Pydantic models
│   └── loader.py          # YAML loading + env interpolation
├── tracing/
│   └── setup.py           # OpenTelemetry TracerProvider init
├── hardware/
│   ├── detect.py          # platform/GPU/memory detection
│   └── profiles.py        # named profiles → model defaults
├── resolve/
│   ├── registry.py        # (provider, platform) → factory tables
│   └── resolver.py        # config + platform → Pipecat services
├── pipeline/
│   └── builder.py         # services → Pipeline + PipelineTask
├── bus/
│   ├── events.py          # event types + envelope
│   ├── codec.py           # binary audio frame pack/unpack
│   ├── server.py          # WebSocketBus (fan-out, backpressure)
│   ├── observer.py        # Pipecat frame → bus event translator
│   └── tail.py            # `paty bus tail` client
├── tui/
│   ├── app.py             # `paty bus tui` event loop + UIState
│   ├── conversation.py    # Conversation/Turn state
│   ├── layout.py          # Rich Layout split tree
│   └── widgets/
│       ├── transcript.py
│       ├── avatar.py
│       └── equalizer.py
└── utils/
    └── env.py             # ${VAR} interpolation
```
