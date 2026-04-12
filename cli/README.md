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
paty profiles                List hardware profiles and their model selections
paty init                    Scaffold a starter config (coming soon)
paty doctor                  Check dependencies (coming soon)
paty eject <config.yaml>     Generate standalone bot.py (coming soon)
```

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
└── utils/
    └── env.py             # ${VAR} interpolation
```
