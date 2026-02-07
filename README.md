
```text
┌───┐   ██████   █████   ██████   ██. ██
│ • │   █    █   █   █     ██     ██████
│ • │   ██████   █████     ██       ██
└───┘   █        █   █     ██       ██
        █        █   █     ██       ██
```

## Project Structure

This project consists of two components:

| Component | Description |
|-----------|-------------|
| **`/pipecat_outbound`** | Pipecat voice bot for outbound calls via Daily |
| **`/mcp`** | MCP server to control the voice agent |

### Voice Bot (`/pipecat_outbound`)

The voice bot (PATY) makes outbound calls and maintains a warm, polite conversation following the PATY protocol:
- Always maintains a courteous tone
- Starts requests with "Please"
- Responds with "Thank you" when receiving information

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
uv run python -m pipecat_outbound.bot --help
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

## Tests

```console
uv run pytest tests/ -v
```

## Deploying to Fly.io

Both components are deployed to Fly.io. Push to `main` to trigger deployment, or use the deploy script:

```bash
./scripts/deploy-fly.sh [bot|mcp|all]
```

### Using the Deployed MCP Server

Run the setup script to generate a project-local `.mcp.json` config:
```bash
./scripts/get-mcp-config.sh
```

This creates a `.mcp.json` file in the project root with the `paty-control` MCP server configured. Restart your coding agent to pick up the new configuration.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
