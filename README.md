PATY (Please And Thank You) is the low latency AI assistant for communicating on your behalf.


## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Silero VAD │ ──▶ │   Faster-   │ ──▶ │  Vertex AI  │ ──▶ │   Kokoro    │
│    (CPU)    │     │   Whisper   │     │    Flash    │     │    TTS      │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
     ~30ms              ~150ms            ~200-500ms            ~50-80ms
```

**Key optimizations:**
- Silero VAD detects speech end → triggers STT immediately
- TTS starts on first sentence boundary (doesn't wait for full LLM response)
- All models stay warm in VRAM (no cold starts)
- Audio streams in chunks for minimal perceived latency

## Requirements

- Python 3.10+
- NVIDIA GPU with CUDA (tested on 3090)
- ~6GB VRAM total
- Google Cloud credentials for## Installation

Prerequisite: Install [uv](https://github.com/astral-sh/uv).

```bash
# Clone and setup
cd PATY

# Install dependencies
brew install portaudio
uv sync
```

## Google Cloud Setup

```bash
# Authenticate
gcloud auth application-default login

# Set project
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
```

## Usage

### Basic Usage

```bash
# Run the MCP Server (formerly main.py)
uv run inference.py
```

### Voice Assistant (main2.py)

```bash
uv run main.py \
  --whisper-model medium.en \
  --sample-rate 16000 \
  --voice af_heart \
  --project your-gcp-project
```

### Configuration Options

| Flag | Default | Description |
|------|---------|-------------|
| `--whisper-model` | `small.en` | Whisper model size |
| `--sample-rate` | `16000` | Audio sample rate |
| `--voice` | `af_heart` | Kokoro voice ID |
| `--project` | env var | GCP project ID |
| `--location` | `us-central1` | Vertex AI location |
| `--system-prompt` | (default) | Custom system prompt |

## (Eventual) Project Structure

```
PATY/
├── main.py              # Entry point and orchestration
├── stt.py               # Speech-to-text (Faster-Whisper)
├── tts.py               # Text-to-speech (Kokoro)
├── llm.py               # Vertex AI Flash client
├── vad.py               # Voice activity detection
├── audio_io.py          # Microphone/speaker handling
└── utils.py             # Sentence detection, audio utils
└── ...
```

## Latency Breakdown

| Component | Typical Latency | Notes |
|-----------|-----------------|-------|
| VAD | ~30ms | Runs on CPU, very fast |
| STT | 100-200ms | GPU, beam_size=1 |
| LLM (first token) | 200-400ms | Network + inference |
| TTS (first chunk) | 50-80ms | GPU, streams output |
| **Total to first audio** | **~400-700ms** | With streaming optimizations |

## Tuning for Lower Latency

### STT
```python
# In stt.py - trade accuracy for speed
model = WhisperModel("small.en", device="cuda", compute_type="float16")
segments, _ = model.transcribe(audio, beam_size=1, best_of=1)
```

### TTS
```python
# In tts.py - smaller chunk size = lower latency, more overhead
CHUNK_MS = 150  # Default 200ms, can go lower
```

### VAD
```python
# In vad.py - faster detection, may cut off speech
MIN_SILENCE_MS = 300  # Default 500ms
```

## Kokoro Voices

| Voice ID | Description |
|----------|-------------|
| `af_heart` | American female, warm |
| `af_bella` | American female, clear |
| `am_adam` | American male, neutral |
| `am_michael` | American male, deep |
| `bf_emma` | British female |
| `bm_george` | British male |

See [Kokoro docs](https://github.com/hexgrad/kokoro) for full list.

## Troubleshooting

### CUDA out of memory
```bash
# Check VRAM usage
nvidia-smi

# Use smaller Whisper model
python main.py --whisper-model tiny.en
```

### Audio device issues
```bash
# List available devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Specify device
python main.py --input-device 1 --output-device 2
```

### High latency spikes
- Ensure models are warm (first request is always slow)
- Check GPU isn't thermal throttling
- Verify network latency to Vertex AI

## License

MIT
