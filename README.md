
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
| **`/voice`** | Voice AI agent for outbound calls |
| **`/mcp`** | MCP server to control the voice agent |

### Voice Agent (`/voice`)

The voice agent (PATY) makes outbound calls and maintains a warm, polite conversation following the PATY protocol:
- Always maintains a courteous tone
- Starts requests with "Please"
- Responds with "Thank you" when receiving information

Features:
- Voice AI pipeline with [models](https://docs.livekit.io/agents/models) from OpenAI, Cartesia, and AssemblyAI
- [LiveKit Turn Detector](https://docs.livekit.io/agents/build/turns/turn-detector/) for multilingual support
- [Background voice cancellation](https://docs.livekit.io/home/cloud/noise-cancellation/)
- Dockerfile ready for [production deployment](https://docs.livekit.io/agents/ops/deployment/)

### MCP Server (`/mcp`)

Control the voice agent via MCP tools:

| Tool | Description |
|------|-------------|
| `make_call` | Initiate an outbound call |
| `end_call` | End an active call |
| `list_rooms` | List active calls |
| `get_call_status` | Get call status |
| `update_participant_config` | Update call configuration |

## Coding Agents and MCP

This project is designed to work with coding agents like [Cursor](https://www.cursor.com/) and [Claude Code](https://www.anthropic.com/claude-code).

To get the most out of these tools, install the [LiveKit Docs MCP server](https://docs.livekit.io/mcp).

For Cursor, use this link:

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/en-US/install-mcp?name=livekit-docs&config=eyJ1cmwiOiJodHRwczovL2RvY3MubGl2ZWtpdC5pby9tY3AifQ%3D%3D)

For Claude Code, run this command:

```
claude mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

For Codex CLI:
```
codex mcp add --url https://docs.livekit.io/mcp livekit-docs
```

For Gemini CLI:
```
gemini mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

The project includes a complete [AGENTS.md](AGENTS.md) file for these assistants.

## Dev Setup

1. Clone the repository:
```console
git clone <repo-url>
cd PATY
```

2. Sign up for [LiveKit Cloud](https://cloud.livekit.io/) and set up the environment:
```console
cp .env.example .env.local
# Fill in LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
```

Or use the [LiveKit CLI](https://docs.livekit.io/home/cli/cli-setup):
```bash
lk cloud auth
lk app env -w -d .env.local
```

3. Configure your SIP trunk in `participant.json`:
```json
{
  "sip_number": "+1XXXXXXXXXX",
  "sip_trunk_id": "ST_XXXXX",
  "sip_call_to": "+1XXXXXXXXXX"
}
```

## Running the Voice Agent

```console
cd voice
uv sync
uv run python src/agent.py download-files  # First time only
uv run python src/agent.py console          # Test in terminal
uv run python src/agent.py dev              # Run for frontend/telephony
```

## Running the MCP Server

```console
cd mcp
uv sync
uv run python src/server.py
```

To add the PATY MCP server to Claude Code:
```bash
claude mcp add paty-control "uv run --directory /path/to/PATY/mcp python src/server.py"
```

## Tests

Run tests for the voice agent:
```console
cd voice
uv run pytest -v
```

## Deploying to Cloud Run

Both components can be deployed to Google Cloud Run. The project includes a GitHub Actions workflow for automated deployments.

### One-time Setup

1. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)

2. Run the setup script:
```bash
export GCP_PROJECT_ID=your-project-id
export GITHUB_REPO=owner/repo
./scripts/setup-gcp.sh
```

3. Add the following secrets to your GitHub repository:
   - `GCP_PROJECT_ID` - Your Google Cloud project ID
   - `WIF_PROVIDER` - Workload Identity Federation provider (from setup script)
   - `WIF_SERVICE_ACCOUNT` - Service account email (from setup script)
   - `LIVEKIT_URL` - Your LiveKit Cloud URL
   - `LIVEKIT_API_KEY` - Your LiveKit API key
   - `LIVEKIT_API_SECRET` - Your LiveKit API secret
   - `SIP_OUTBOUND_TRUNK_ID` - Your SIP trunk ID

4. Optionally set `GCP_REGION` as a repository variable (defaults to `us-central1`)

### Automatic Deployment

Push to `main` to trigger deployment of both services, or use the "Run workflow" button in GitHub Actions to deploy selectively.

### Manual Deployment

Build and deploy locally:

```bash
# Voice agent
cd voice
docker build -t paty-voice .
gcloud run deploy paty-voice --source .

# MCP server
cd mcp
docker build -t paty-mcp .
gcloud run deploy paty-mcp --source .
```

### Using the Deployed MCP Server

Once deployed, run the setup script to generate a project-local `.mcp.json` config:
```bash
./scripts/get-mcp-config.sh
```

This creates a `.mcp.json` file in the project root with both the `paty-control` and `livekit-docs` MCP servers configured. Restart your coding agent to pick up the new configuration.

The `.mcp.json` file is gitignored since it contains your deployment-specific URL.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
