
```text
┌───┐   ██████   █████   ██████   ██  ██
│ • │   █    █   █   █     ██     ██████
│ • │   ██████   █████     ██       ██
└───┘   █        █   █     ██       ██
```
PATY is entirely local. And therefore, is entirely free.

# Install & run

Prerequisites: **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)**.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # if you don't already have uv
uv tool install paty
paty run
```

`paty run` with no argument loads a bundled default config. The first run will detect your platform and tell you which extra to install for local inference:

```bash
uv tool install 'paty[mlx]'    # Apple Silicon
uv tool install 'paty[cuda]'   # NVIDIA GPU
uv tool install 'paty[cpu]'    # CPU fallback
```

Then `paty run` again. First launch downloads the LLM and STT models (a few GB) and is slow; subsequent runs reuse the Hugging Face cache.

CUDA/CPU users also need a [Kokoro FastAPI](https://github.com/remsky/Kokoro-FastAPI) server on `localhost:8880` for TTS — Apple Silicon runs Kokoro in-process.

See [`cli/README.md`](cli/README.md) for the config schema, CLI commands, hardware profiles, the event bus, and dev setup.

# Themes
![Night](docs/materials/PATYCLINight.png)
![Day](docs/materials/PATYCLIDay.png)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
