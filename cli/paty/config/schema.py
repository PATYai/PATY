"""Pydantic models for the PATY YAML config schema."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, model_validator


class HardwareProfile(StrEnum):
    AUTO = "auto"
    APPLE_16GB = "apple-16gb"
    APPLE_24GB = "apple-24gb"
    CUDA_24GB = "cuda-24gb"
    CPU_ONLY = "cpu-only"


class Platform(StrEnum):
    MLX = "mlx"
    CUDA = "cuda"
    CPU = "cpu"


# --- Agent ---


class AgentConfig(BaseModel):
    name: str
    persona: str
    flow: str | None = None


# --- Pipeline services ---


class STTConfig(BaseModel):
    provider: str = "whisper"
    model: str | None = None


class LLMConfig(BaseModel):
    provider: str = "ollama"
    model: str | None = None
    base_url: str | None = None


class TTSConfig(BaseModel):
    provider: str = "kokoro"
    voice: str | None = None
    base_url: str | None = None


class PipelineConfig(BaseModel):
    """Pipeline config with string shorthand normalization.

    Accepts either ``"whisper"`` or ``{"provider": "whisper", "model": "..."}``
    for each service entry.
    """

    stt: STTConfig = STTConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()
    vad: str = "silero"

    @model_validator(mode="before")
    @classmethod
    def normalize_service_entries(cls, data: dict) -> dict:
        for key in ("stt", "llm", "tts"):
            if key in data and isinstance(data[key], str):
                data[key] = {"provider": data[key]}
        return data


# --- Hardware ---


class HardwareConfig(BaseModel):
    profile: HardwareProfile = HardwareProfile.AUTO


# --- SIP ---


class SIPConfig(BaseModel):
    provider: str | None = None
    host: str | None = None
    username: str | None = None
    password: str | None = None
    did: str | None = None


# --- Tracing ---


class TracingConfig(BaseModel):
    enabled: bool = True
    console: bool = True
    otlp_endpoint: str | None = None
    service_name: str = "paty"


# --- Metrics ---


class MetricsConfig(BaseModel):
    enabled: bool = True
    console_interval: int = 10  # seconds between Rich table prints (0 = disable)
    prometheus: bool = False  # start :prometheus_port/metrics endpoint
    prometheus_port: int = 9464


# --- Bus ---


class BusConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765


# --- PAK ---


class PakConfig(BaseModel):
    """Selects which PAK provides the persona and voice for this run.

    ``active=None`` means *fall back to the bundled default PAK* — set
    explicitly to load one named PAK from the registry.
    """

    active: str | None = None
    paks_dir: str | None = None


# --- Top-level ---


class PatyConfig(BaseModel):
    """Either ``agent`` (legacy inline persona) or ``pak`` may drive the
    persona — never both.  Specifying neither falls back to the bundled
    ``paty`` PAK at runtime.
    """

    agent: AgentConfig | None = None
    pak: PakConfig = PakConfig()
    pipeline: PipelineConfig = PipelineConfig()
    hardware: HardwareConfig = HardwareConfig()
    sip: SIPConfig = SIPConfig()
    tracing: TracingConfig = TracingConfig()
    metrics: MetricsConfig = MetricsConfig()
    bus: BusConfig = BusConfig()

    @model_validator(mode="after")
    def _legacy_and_pak_are_mutually_exclusive(self) -> PatyConfig:
        if self.agent is not None and self.pak.active is not None:
            msg = "Specify either `agent.persona` (legacy) or `pak.active`, not both."
            raise ValueError(msg)
        return self
