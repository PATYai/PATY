
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
paty run
```

`paty run` with no argument loads a bundled default config. The first run will detect your platform and tell you which extra to install for local inference:

```bash
uv tool install 'paty[mlx]'    # Apple Silicon
uv tool install 'paty[cuda]'   # NVIDIA GPU -- coming soon
```

Then `paty run` again. First launch downloads the LLM and STT models (a few GB) and is slow; subsequent runs reuse the Hugging Face cache.

# PAKs (Personality Augmentation Kits)
Don't like the voice? Run `paty pak switch`. `nova` is bundled.
```
paty pak switch nova
```

# PAKs (Personality Augmentation Kits)
Want to change your voice and personality? Switch PAKs.
```
paty pak switch nova
```
PATY ships with two paks: Paty and Nova

# Themes
![Night](docs/materials/PATYCLINight.png)
![Day](docs/materials/PATYCLIDay.png)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
