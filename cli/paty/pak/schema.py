"""Pydantic models for the PATY PAK manifest (``pak.yaml``)."""

from __future__ import annotations

from pydantic import BaseModel


class PakTTSConfig(BaseModel):
    """TTS settings declared by a PAK.

    The TTS provider is part of a PAK's identity — Nova may use one model,
    Coach another. ``voice`` is optional so authors can ship a PAK that
    inherits the hardware profile's default voice for the chosen provider.
    """

    provider: str = "kokoro"
    voice: str | None = None


class PakLLMConfig(BaseModel):
    """LLM model pin.

    ``None`` means *inherit from the hardware profile* — the common case.
    Pinning a model is allowed but expensive: switching to or from a
    differently-pinned PAK forces a full LLM reload. The CLI logs a loud
    warning at startup when a pin disagrees with the resolved profile.
    """

    model: str | None = None


class PakVoiceConfig(BaseModel):
    tts: PakTTSConfig = PakTTSConfig()
    llm: PakLLMConfig = PakLLMConfig()


class PakConversationConfig(BaseModel):
    """How much of this PAK's history to load on session start, and how long
    to keep it on disk.  Storage lives outside the PAK directory so a PAK can
    be redistributed without leaking personal chat data.
    """

    retention_days: int = 30
    max_turns_loaded: int = 50


class PakMetadata(BaseModel):
    name: str
    version: str = "0.0.1"
    description: str = ""
    soul: str = "soul.md"


class PakManifest(BaseModel):
    """Top-level structure of ``pak.yaml``.

    The ``heartbeats`` field is intentionally absent from this version of
    the schema; it is reserved for a follow-up MR that will add scheduled
    background prompts.  Adding it later is non-breaking.
    """

    pak: PakMetadata
    voice: PakVoiceConfig = PakVoiceConfig()
    conversation: PakConversationConfig = PakConversationConfig()
