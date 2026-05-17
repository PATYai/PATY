
```text
┌───┐   ██████   █████   ██████   ██  ██
│ • │   █    █   █   █     ██     ██████
│ • │   ██████   █████     ██       ██
└───┘   █        █   █     ██       ██
```
PATY is entirely local. And therefore, is entirely free.

# Install & run

Prerequisites: **[uv](https://docs.astral.sh/uv/)** and **[portaudio](https://github.com/PortAudio/portaudio)**. The happy path is for MacOS on Apple Silicon. CUDA coming soon.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # if you don't already have uv
brew install portaudio
uv tool install paty
paty
```

Bare `paty` (no subcommand) shows a DOS-style boot screen while the agent warms up, then auto-hands off to the live TUI once it's ready. Use `paty run` if you want the raw agent without the boot UI / TUI. Either form with no config argument loads a bundled default config; the first run will detect your platform and tell you which extra to install for local inference:

```bash
uv tool install 'paty[mlx]'    # Apple Silicon
uv tool install 'paty[cuda]'   # NVIDIA GPU -- coming soon
```

Then `paty` again. First launch downloads the LLM and STT models (a few GB) and is slow; subsequent runs reuse the Hugging Face cache.

CUDA users also need a [Kokoro FastAPI](https://github.com/remsky/Kokoro-FastAPI) server on `localhost:8880` for TTS — Apple Silicon runs Kokoro in-process.

See [`cli/README.md`](cli/README.md) for the config schema, CLI commands, hardware profiles, the event bus, and dev setup.

# Building locally

To run `paty` from a clone of this repo (instead of `uv tool install paty`):

```bash
git clone https://github.com/PATYai/PATY.git
cd PATY/cli
uv sync --extra mlx            # Apple Silicon
# uv sync --extra cuda         # NVIDIA GPU -- coming soon
uv run paty                    # boot screen → TUI; use `uv run paty run` for the raw agent
```

Notes:

- The base `uv sync` does not install an inference backend — pick `--extra mlx` (or `--extra cuda` once CUDA lands). Without one, `paty run` exits with "No backend installed."
- Add `--extra dev` if you also want to run tests/lint (`pytest`, `ruff`).
- `cuda` builds `llama-cpp-python` from source and needs a working C/C++ + CUDA toolchain.
- CUDA users also need a [Kokoro FastAPI](https://github.com/remsky/Kokoro-FastAPI) server on `localhost:8880` for TTS; Apple Silicon runs Kokoro in-process.
- First run downloads the LLM + STT weights (a few GB) into the Hugging Face cache.

# PAKs (Personality Augmentation Kits)
Don't like the voice? Run `paty pak switch`. `nova` is bundled.
```
paty pak switch nova
```
![Demo](docs/materials/PATYDemo.mov)

# Themes
PATY ships with a TUI. Run it in a separate window to mute or chat.
```
paty bus tui
```
![Night](docs/materials/PATYCLINight.png)
![Day](docs/materials/PATYCLIDay.png)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
