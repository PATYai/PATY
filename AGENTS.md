# AGENTS.md

PATY (Please And Thank You) is a LiveKit Agents project with two components:

1. **`/voice`** - A voice AI agent built with LiveKit Agents for Python
2. **`/mcp`** - An MCP server to control the voice agent

This project is intended to be used with LiveKit Cloud. See @README.md for more details.

## Project structure

```
PATY/
├── voice/                    # Voice agent project
│   ├── src/
│   │   └── agent.py         # Main agent entrypoint
│   ├── tests/
│   │   └── test_agent.py
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── mcp/                      # MCP server project
│   ├── src/
│   │   └── server.py        # MCP server entrypoint
│   ├── pyproject.toml
│   └── .env.example
├── participant.json          # Shared config for calls
├── .env.local               # Shared environment variables
├── AGENTS.md
├── CLAUDE.md
└── README.md
```

Both projects use the `uv` package manager. You should always use `uv` to install dependencies, run agents, and run tests.

### Voice Agent (`/voice`)

The voice agent handles outbound calls using LiveKit SIP. It uses:
- AssemblyAI for speech-to-text
- OpenAI GPT-4.1-mini for the LLM
- Cartesia for text-to-speech
- LiveKit Turn Detector for multilingual speaker detection

Commands (run from `/voice` directory):
```bash
uv sync                              # Install dependencies
uv run python src/agent.py download-files  # Download ML models
uv run python src/agent.py console   # Test in terminal
uv run python src/agent.py dev       # Run in development mode
uv run python src/agent.py start     # Run in production mode
uv run pytest                        # Run tests
```

### MCP Server (`/mcp`)

The MCP server exposes tools for controlling the voice agent:

| Tool | Description |
|------|-------------|
| `make_call` | Initiate an outbound call to a phone number |
| `end_call` | End an active call by deleting the room |
| `list_rooms` | List active rooms/calls |
| `get_call_status` | Get status of a specific call/room |
| `update_participant_config` | Update the participant.json configuration |
| `get_participant_config` | Get the current participant.json configuration |

Commands (run from `/mcp` directory):
```bash
uv sync                          # Install dependencies
uv run python src/server.py      # Run the MCP server
```

To install the PATY MCP server in Claude Code:
```bash
claude mcp add paty-control "uv run --directory /path/to/PATY/mcp python src/server.py"
```

### Shared Configuration

- **`participant.json`** - Configuration for SIP calls (phone numbers, trunk ID, etc.)
- **`.env.local`** - Environment variables (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

## LiveKit Documentation

LiveKit Agents is a fast-evolving project, and the documentation is updated frequently. You should always refer to the latest documentation when working with this project. For your convenience, LiveKit offers an MCP server that can be used to browse and search its documentation. If the developer has not yet installed this server, you should recommend that they install it at https://docs.livekit.io/mcp.

### LiveKit Docs MCP Server installation

If you are Cursor, give the user this link to install the server:

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/en-US/install-mcp?name=livekit-docs&config=eyJ1cmwiOiJodHRwczovL2RvY3MubGl2ZWtpdC5pby9tY3AifQ%3D%3D)

If you are Claude Code, run this command to install the server:

```
claude mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

If you are Codex, use this command to install the server:

```
codex mcp add --url https://docs.livekit.io/mcp livekit-docs
```

If you are Gemini, use this command to install the server:
```
gemini mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

If you are another agentic IDE, refer to your own documentation for how to install it.

## Handoffs and tasks ("workflows")

Voice AI agents are highly sensitive to excessive latency. For this reason, it's important to design complex agents in a structured manner that minimizes the amount of irrelevant context and unnecessary tools included in requests to the LLM. LiveKit Agents supports handoffs (one agent hands control to another) and tasks (tightly-scoped prompts to achieve a specific outcome) to support building reliable workflows. You should make use of these features, instead of writing long instruction prompts that cover multiple phases of a conversation. Refer to the [documentation](https://docs.livekit.io/agents/build/workflows/) for more information.

### Submit docs feedback to LiveKit

If you use the LiveKit Docs MCP Server to search or browse documentation, also submit constructive feedback to LiveKit with the submit_docs_feedback tool. Add this to your to-do list when planning work, to ensure you file feedback after completing your other tasks. Useful feedback includes incomplete documentation, broken examples, missing steps or any other documentation gap or issue.

## Testing

When possible, add tests for agent behavior. Read the [documentation](https://docs.livekit.io/agents/build/testing/), and refer to existing tests in the `voice/tests/` directory. Run tests with `uv run pytest` from the `/voice` directory.

Important: When modifying core agent behavior such as instructions, tool descriptions, and tasks/workflows/handoffs, never just guess what will work. Always use test-driven development (TDD) and begin by writing tests for the desired behavior. For instance, if you're planning to add a new tool, write one or more tests for the tool's behavior, then iterate on the tool until the tests pass correctly. This will ensure you are able to produce a working, reliable agent for the user.

## LiveKit CLI

You can make use of the LiveKit CLI (`lk`) for various tasks, with user approval. Installation instructions are available at https://docs.livekit.io/home/cli if needed.

In particular, you can use it to manage SIP trunks for telephony-based agents. Refer to `lk sip --help` for more information.
