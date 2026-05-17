
```text
┌───┐   ██████   █████   ██████   ██  ██
│ • │   █    █   █   █     ██     ██████
│ • │   ██████   █████     ██       ██
└───┘   █        █   █     ██       ██
```
PATY is entirely local. And therefore, is entirely free.

# Install & run

Prerequisites: **[uv](https://docs.astral.sh/uv/)**.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # if you don't already have uv
uv tool install paty
paty
```

Bare `paty` (no subcommand) shows a DOS-style boot screen while the agent warms up, then auto-hands off to the live TUI once it's ready. Use `paty run` if you want the raw agent without the boot UI / TUI. Either form with no config argument loads a bundled default config; the first run will detect your platform and tell you which extra to install for local inference:

```bash
uv tool install 'paty[mlx]'    # Apple Silicon
uv tool install 'paty[cuda]'   # NVIDIA GPU
uv tool install 'paty[cpu]'    # CPU fallback
```

Then `paty` again. First launch downloads the LLM and STT models (a few GB) and is slow; subsequent runs reuse the Hugging Face cache.

CUDA/CPU users also need a [Kokoro FastAPI](https://github.com/remsky/Kokoro-FastAPI) server on `localhost:8880` for TTS — Apple Silicon runs Kokoro in-process.

See [`cli/README.md`](cli/README.md) for the config schema, CLI commands, hardware profiles, the event bus, and dev setup.

# Building locally

To run `paty` from a clone of this repo (instead of `uv tool install paty`):

```bash
git clone https://github.com/PATYai/PATY.git
cd PATY/cli
uv sync --extra mlx            # Apple Silicon
# uv sync --extra cuda         # NVIDIA GPU
# uv sync --extra cpu          # CPU fallback
uv run paty                    # boot screen → TUI; use `uv run paty run` for the raw agent
```

Notes:

- The base `uv sync` does not install an inference backend — pick exactly one of `--extra mlx`, `--extra cuda`, or `--extra cpu`. Without one, `paty run` exits with "No backend installed."
- Add `--extra dev` if you also want to run tests/lint (`pytest`, `ruff`).
- `cuda` / `cpu` builds `llama-cpp-python` from source and need a working C/C++ toolchain (and CUDA toolchain for `cuda`).
- CUDA/CPU users also need a [Kokoro FastAPI](https://github.com/remsky/Kokoro-FastAPI) server on `localhost:8880` for TTS; Apple Silicon runs Kokoro in-process.
- First run downloads the LLM + STT weights (a few GB) into the Hugging Face cache.

# Themes
![Night](docs/materials/PATYCLINight.png)
![Day](docs/materials/PATYCLIDay.png)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
