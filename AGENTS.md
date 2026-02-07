# AGENTS.md

## Workflow

- **Always lint before considering work done.** Run `uv run --directory mcp ruff check src/` for MCP changes and `uv run ruff check pipecat_outbound/` for bot changes.

## Overview

PATY (Please And Thank You) is a voice AI project with two components:

1. **`/pipecat_outbound`** - A Pipecat-based voice bot for outbound calls via Daily
2. **`/mcp`** - An MCP server to control the voice agent

This project uses Daily for telephony (dial-out) and Pipecat for the voice AI pipeline.

## Project structure

```
PATY/
├── pipecat_outbound/            # Pipecat voice bot (primary)
│   ├── __init__.py
│   ├── bot.py                  # Main voice bot
│   ├── caller.py               # Outbound call management
│   ├── protocol.py             # Provider abstractions
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
