
```text
┌───┐   ██████   █████   ██████   ██  ██
│ • │   █    █   █   █     ██     ██████
│ • │   ██████   █████     ██       ██
└───┘   █        █   █     ██       ██
```
A voice assistant focused on self-hosting.
## 🚧 Project Structure

You can use PATY now. Plug it into ChatGPT or Claude with the MCP server.
```
https://paty-stage-mcp.fly.dev/mcp
```
No authentication required.

This project consists of three components:

| Component | Description |
|-----------|-------------|
| **`/agent`** | Framework-agnostic intelligence: prompts, protocol, HTTP server, call simulator |
| **`/pipecat_outbound`** | Pipecat-based voice pipeline and telephony providers |
| **`/mcp`** | MCP server to control the voice agent |

### Agent Intelligence (`/agent`)

The agent layer owns PATY's personality, system prompt, call protocol, and HTTP server. It has no dependency on Pipecat, so it can be tested and reused independently.

- **`prompt.py`** — System prompt construction (PATY protocol: "Please" and "Thank you")
- **`protocol.py`** — `CallRequest`, `CallSession`, `OutboundProvider` ABC
- **`server.py`** — FastAPI HTTP server (session management, transcripts, live instructions)
- **`simulator/`** — IVR and human-persona call simulators for automated testing

### Voice Pipeline (`/pipecat_outbound`)

The voice bot makes outbound calls using Pipecat with Daily for WebRTC transport.

**Stack:**
- **Transport**: Daily WebRTC
- **STT**: AssemblyAI
- **LLM**: OpenAI GPT-4
- **TTS**: Cartesia

### MCP Server (`/mcp`)

Control the voice agent via MCP tools:

| Tool | Description |
|------|-------------|
| `make_call` | Initiate an outbound call |
| `end_call` | End an active call |
| `list_rooms` | List active calls |
| `get_call_status` | Get call status |
| `get_transcript` | Get live call transcript |
| `send_instruction` | Send a live instruction to the bot |

## Dev Setup

1. Clone the repository:
```console
git clone <repo-url>
cd PATY
```

2. Set up the environment:
```console
cp .env.example .env.local
# Fill in DAILY_API_KEY, OPENAI_API_KEY, CARTESIA_API_KEY, ASSEMBLYAI_API_KEY
```

## Running the Voice Bot

```console
uv sync
uv run uvicorn agent.server:app --host 0.0.0.0 --port 8080
```

## Running the MCP Server

```console
cd mcp
uv sync
MCP_AUTH_DISABLED=true uv run python src/server.py
```

To add the PATY MCP server to Claude Code:
```bash
claude mcp add paty-control "uv run --directory /path/to/PATY/mcp python src/server.py"
```

## Tracing

The bot emits OpenTelemetry traces for each conversation turn, with spans for STT, LLM, and TTS. It also logs turn completion/interruption events via `TurnTrackingObserver`.

### Local (Jaeger)

Start Jaeger, then run the bot as normal — traces are sent to `localhost:4317` by default:

```bash
docker run -d --name jaeger -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one:latest
```

View traces at http://localhost:16686, service name `paty-bot`.

### Production (Honeycomb)

Set these env vars (or Fly secrets) to export traces to Honeycomb:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io:443
OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=<your-api-key>
```

## Tests

```console
uv run pytest tests/unit               # Unit tests
uv run pytest tests/http -v            # HTTP endpoint tests
uv run pytest tests/simulator -v       # Simulator tests (requires OPENAI_API_KEY)
uv run pytest tests/smoke              # Smoke tests (requires DAILY_API_KEY)
```

### Call Simulator

The simulator (`agent/simulator/`) supports two modes:

- **IVR**: State-machine phone menus with regex-matched transitions. Tests that PATY can navigate multi-level IVR trees to reach a live agent.
- **Human persona**: Sequential pattern-matched conversations. Tests that PATY can handle post-IVR interactions like filing claims or booking appointments.

Scenarios are defined in YAML (`tests/simulator/scenarios/`) and run at two levels:
- **Transcript-level** (every PR): text-only loop with a real LLM, no audio services needed
- **Waveform-level** (merge to main): full TTS→STT round-trip to catch audio fidelity issues

## Deploying to Fly.io

All three components are deployed to Fly.io.

### First-time setup

Create the apps, set secrets from `.env.local`, and deploy:

```bash
./scripts/setup-fly.sh
```

### Subsequent deploys

```bash
./scripts/deploy-fly.sh [bot|mcp|web|all]
```

### Using the Deployed MCP Server

Run the setup script to generate a project-local `.mcp.json` config:
```bash
./scripts/get-mcp-config.sh
```

This creates a `.mcp.json` file in the project root with the `paty-control` MCP server configured. Restart your coding agent to pick up the new configuration.

## Architecture

### Call Flow

1. **MCP Server** receives `make_call` request with phone number and goal
2. Server creates a **Daily room** configured for dial-out
3. Server spawns **Pipecat bot** via HTTP POST to the bot service
4. Bot joins Daily room and initiates **PSTN dial-out**
5. When callee answers, bot conducts conversation using LLM
6. Call ends when callee hangs up or `end_call` is called

### Voice Pipeline

```
Phone Audio → Daily Transport → AssemblyAI STT → OpenAI LLM → Cartesia TTS → Daily Transport → Phone Audio
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
