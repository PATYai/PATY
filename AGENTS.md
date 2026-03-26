# AGENTS.md

## Workflow

- **Always lint before considering work done.** Run `uv run --directory mcp ruff check src/` for MCP changes and `uv run ruff check agent/ pipecat_outbound/` for bot/agent changes.

## Testing the ChatGPT Mini-App (`mcp/ui`)

The transcript mini-app (`mcp/ui/src/App.tsx`) can be tested locally without ChatGPT using a Playwright-based mock host:

```bash
cd mcp/ui
npm install
npm run build
node test-local.mjs
```

`test-local.mjs` serves the built app in an iframe, acts as a mock ChatGPT host (responds to `ui/initialize`, pushes a fake `ui/notifications/tool-result`), and prints the app's rendered content + debug panel.

**What a passing run looks like:**
- App content shows `PATY · LIVE · paty-test-deadbeef · Dialing…`
- Host logs show `tools/call` for `get_transcript` being invoked (proves polling started)
- "Dialing…" is expected — advancing past it requires a real bot session

**Key protocol notes learned during debugging:**
- `App.connect()` requires an explicit `new PostMessageTransport()` argument (no default)
- `ontoolresult` receives `{ toolInput, toolResult: CallToolResult, content: [] }` — the actual tool output is in `.toolResult.content`, NOT `.content`
- `PostMessageTransport(target, source)` — defaults to `window.parent` as target; must be in a real iframe for correct source filtering

## Overview

PATY (Please And Thank You) is a voice AI project with three components:

1. **`/agent`** - Framework-agnostic intelligence: prompts, protocol, HTTP server, call simulator
2. **`/pipecat_outbound`** - Pipecat-based voice pipeline and telephony providers
3. **`/mcp`** - An MCP server to control the voice agent

This project uses Daily for telephony (dial-out) and Pipecat for the voice AI pipeline.

## Project structure

```
PATY/
├── agent/                       # Agent intelligence layer
│   ├── __init__.py
│   ├── prompt.py               # System prompt construction
│   ├── protocol.py             # CallRequest, CallSession, OutboundProvider ABC
│   ├── server.py               # FastAPI HTTP server (session mgmt, transcripts)
│   └── simulator/              # Call simulation engines
│       ├── engine.py           # IVRSimulator, PersonaSimulator
│       └── scenario.py         # YAML scenario loader
├── pipecat_outbound/            # Pipecat voice pipeline
│   ├── __init__.py
│   ├── bot.py                  # Voice bot (STT→LLM→TTS pipeline)
│   ├── caller.py               # Outbound call routing
│   ├── telephony.yaml          # Provider configuration
│   └── providers/
│       └── daily.py            # Daily.co provider
├── mcp/                         # MCP server project
│   ├── src/
│   │   └── server.py           # MCP server entrypoint
│   ├── pyproject.toml
│   └── .env.example
├── tests/                       # Shared tests
│   ├── unit/
│   ├── http/
│   ├── simulator/              # IVR/human simulation tests
│   └── smoke/
├── .env.local                   # Environment variables
├── pyproject.toml               # Root project config
├── AGENTS.md
└── README.md
```

All projects use the `uv` package manager.

## Pipecat Voice Bot (`/pipecat_outbound`)

The voice bot uses Pipecat with Daily for outbound phone calls. It implements the PATY protocol (Please And Thank You) for polite, low-latency conversations.

**Stack:**
- **Transport**: Daily WebRTC
- **STT**: AssemblyAI
- **LLM**: OpenAI GPT-4
- **TTS**: Cartesia

Commands (run from project root):
```bash
uv sync                                      # Install dependencies
uv run python -m pipecat_outbound.bot --help # Show bot options
uv run pytest tests/                         # Run tests
```

## MCP Server (`/mcp`)

The MCP server exposes tools for controlling the voice agent via Daily:

| Tool | Description |
|------|-------------|
| `make_call` | Initiate an outbound call to a phone number |
| `end_call` | End an active call by deleting the room |
| `list_rooms` | List active rooms/calls |
| `get_call_status` | Get status of a specific call/room |

Commands (run from `/mcp` directory):
```bash
uv sync                          # Install dependencies
MCP_AUTH_DISABLED=true uv run python src/server.py  # Run locally
```

To install the PATY MCP server in Claude Code:
```bash
claude mcp add paty-control "uv run --directory /path/to/PATY/mcp python src/server.py"
```

## Environment Variables

Required in `.env.local`:

```bash
# Daily API (for telephony)
DAILY_API_KEY=your_daily_api_key

# AI Services
OPENAI_API_KEY=your_openai_key
CARTESIA_API_KEY=your_cartesia_key
ASSEMBLYAI_API_KEY=your_assemblyai_key
```

**Note:** PSTN dial-out requires a Daily plan with telephony enabled. Contact Daily to upgrade your account for outbound phone calls.

## Pipecat Documentation

Pipecat is a framework for building voice and multimodal conversational AI. For documentation:
- [Pipecat Docs](https://docs.pipecat.ai)
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)
- [Daily PSTN Dial-out Guide](https://docs.pipecat.ai/deployment/pipecat-cloud/guides/telephony/daily-dial-out)

## Testing

Run tests from the project root:
```bash
uv run pytest tests/unit          # Unit tests
uv run pytest tests/smoke         # Smoke tests (requires API keys)
```

## Architecture

### Call Flow

1. **MCP Server** receives `make_call` request with phone number
2. Server creates a **Daily room** configured for dial-out
3. Server spawns **Pipecat bot** subprocess
4. Bot joins Daily room and initiates **PSTN dial-out**
5. When callee answers, bot conducts conversation using LLM
6. Call ends when callee hangs up or `end_call` is called

### Voice Pipeline

```
Phone Audio -> Daily Transport -> AssemblyAI STT -> OpenAI LLM -> Cartesia TTS -> Daily Transport -> Phone Audio
```
