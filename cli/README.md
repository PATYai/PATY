# PATY — Please & Thank You

Declarative voice agent deployment on Pipecat. Write a YAML config, run `paty run config.yaml`, get a working voice agent. No `bot.py` to write.

## Quickstart

```bash
cd cli
uv sync
uv run paty run ../examples/paty.yaml
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

- **Text frames** — JSON control events with envelope `{v, seq, ts_ms, session_id, type, data}`. Types cover session lifecycle (`session.started`, `session.ended`), user turn (`user.speech_started/stopped`, `user.transcript.partial/final`), agent turn (`agent.thinking_started`, `agent.response.delta/completed`, `agent.speech_started/stopped`), derived `state.changed` (idle/listening/thinking/speaking), `metrics.tick`, and `error`/`log`.
- **Binary frames** — a 16-byte header followed by PCM16LE audio samples. Header: `magic(1)`, `version(1)`, `stream(1: 1=mic, 2=agent)`, `reserved(1)`, `sample_rate(u16 LE)`, `channels(u16 LE)`, `seq(u32 LE)`, `ts_ms(u32 LE)` since session start.

v1 is publisher-only — inbound messages from subscribers are discarded. The server fans out to any number of subscribers; control events never drop (overflow disconnects the slow subscriber), audio frames drop-oldest under backpressure.

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

## Development

```bash
uv sync --extra dev
uv run pytest tests/ -v         # run tests
uv run ruff check paty/ tests/  # lint
uv run ruff format paty/ tests/ # format
```

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
