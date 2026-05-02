"""Service registries: (provider, platform) → Pipecat service factory.

Each factory receives a resolved config object (STTConfig, LLMConfig, TTSConfig)
with model/voice already filled in (from explicit override or profile default),
plus a ``compute_executor`` that may be None.  MLX factories require it;
CUDA/CPU factories ignore it.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from loguru import logger

from paty.config.schema import LLMConfig, Platform, STTConfig, TTSConfig
from paty.hardware.profiles import ResolvedProfile

# Type alias for factory functions
Factory = Callable[..., Any]

# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

STT_REGISTRY: dict[tuple[str, Platform], Factory] = {
    ("mlx-audio", Platform.MLX): lambda cfg, p, ex: _make_mlx_audio_stt(cfg, ex),
    ("whisper", Platform.MLX): lambda cfg, p, ex: _make_whisper(cfg, "auto", p),
    ("whisper", Platform.CUDA): lambda cfg, p, ex: _make_whisper(cfg, "cuda", p),
    ("whisper", Platform.CPU): lambda cfg, p, ex: _make_whisper(cfg, "cpu", p),
}


def _make_mlx_audio_stt(cfg: STTConfig, executor: ThreadPoolExecutor | None) -> Any:
    if executor is None:
        msg = "mlx-audio STT requires a shared compute_executor"
        raise ValueError(msg)
    from paty.runtime.stt_service import MLXAudioSTTService

    return MLXAudioSTTService(
        compute_executor=executor,
        model_repo=cfg.model or "UsefulSensors/moonshine-base",
    )


def _make_whisper(cfg: STTConfig, device: str, profile: ResolvedProfile) -> Any:
    from pipecat.services.whisper.stt import WhisperSTTService

    return WhisperSTTService(
        settings=WhisperSTTService.Settings(model=cfg.model),
        device=device,
        compute_type=profile.stt_compute_type,
    )


# ---------------------------------------------------------------------------
# LLM — all platforms use OpenAI-compat client pointed at managed server
# ---------------------------------------------------------------------------

LLM_REGISTRY: dict[tuple[str, Platform], Factory] = {
    ("ollama", Platform.MLX): lambda cfg: _make_openai_compat_llm(cfg),
    ("ollama", Platform.CUDA): lambda cfg: _make_openai_compat_llm(cfg),
    ("ollama", Platform.CPU): lambda cfg: _make_openai_compat_llm(cfg),
}


def _make_openai_compat_llm(cfg: LLMConfig) -> Any:
    from pipecat.services.openai.llm import OpenAILLMService

    return OpenAILLMService(
        model=cfg.model or "default",
        base_url=cfg.base_url or "http://localhost:11434/v1",
        api_key="local",
    )


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

TTS_REGISTRY: dict[tuple[str, Platform], Factory] = {
    ("kokoro", Platform.MLX): lambda cfg, ex: _make_mlx_audio_tts(cfg, ex),
    ("kokoro", Platform.CUDA): lambda cfg, ex: _make_kokoro_http(cfg),
    ("kokoro", Platform.CPU): lambda cfg, ex: _make_kokoro_http(cfg),
    ("piper", Platform.CPU): lambda cfg, ex: _make_piper(cfg),
}


_EN_CORE_WEB_SM_URL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
)


def _ensure_spacy_model_for_misaki() -> None:
    """Make sure `en_core_web_sm` is installed AND importable from this process.

    Misaki uses spaCy's English G2P pipeline, which needs `en_core_web_sm`.
    spaCy's own `download` command shells out to `pip install`, but
    `uv tool` venvs don't have pip — the call appears to succeed (rc=0)
    while landing nothing in the tool's site-packages. We bypass that and
    use `uv pip install --python <ours>` against the model wheel URL,
    which targets the running tool venv directly.
    """
    import importlib
    import shutil
    import subprocess
    import sys

    try:
        importlib.import_module("en_core_web_sm")
        return  # already there
    except ImportError:
        pass

    if shutil.which("uv") is not None:
        cmd = ["uv", "pip", "install", "--python", sys.executable, _EN_CORE_WEB_SM_URL]
    else:
        cmd = [sys.executable, "-m", "pip", "install", _EN_CORE_WEB_SM_URL]

    logger.info(
        f"misaki: installing en_core_web_sm via `{' '.join(cmd[:3])}` (~13MB, one-time)"
    )
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.stdout:
        logger.debug(f"misaki: install stdout:\n{result.stdout}")
    if result.stderr:
        logger.debug(f"misaki: install stderr:\n{result.stderr}")
    if result.returncode != 0:
        msg = (
            f"Failed to install en_core_web_sm (rc={result.returncode}). "
            f"Stderr: {result.stderr}"
        )
        logger.error(msg)
        raise RuntimeError(msg)

    importlib.invalidate_caches()
    try:
        importlib.import_module("en_core_web_sm")
    except ImportError as e:
        logger.error(
            "misaki: en_core_web_sm install reported success but the running "
            f"process still can't import it: {e}.\n"
            f"Install command: {' '.join(cmd)}\n"
            f"Install stdout:\n{result.stdout}\n"
            f"Install stderr:\n{result.stderr}"
        )
        raise

    logger.info("misaki: en_core_web_sm installed and importable")


def _make_mlx_audio_tts(cfg: TTSConfig, executor: ThreadPoolExecutor | None) -> Any:
    if executor is None:
        msg = "mlx-audio TTS requires a shared compute_executor"
        raise ValueError(msg)
    _ensure_spacy_model_for_misaki()
    from paty.runtime.tts_service import MLXAudioTTSService

    return MLXAudioTTSService(
        compute_executor=executor,
        voice=cfg.voice or "af_bella",
    )


def _make_kokoro_http(cfg: TTSConfig) -> Any:
    from pipecat.services.openai.tts import OpenAITTSService

    return OpenAITTSService(
        base_url=cfg.base_url or "http://localhost:8880/v1",
        api_key="local",
        voice=cfg.voice,
    )


def _make_piper(cfg: TTSConfig) -> Any:
    from pipecat.services.piper import PiperTTSService

    return PiperTTSService(
        settings=PiperTTSService.Settings(
            voice=cfg.voice,
        )
    )
