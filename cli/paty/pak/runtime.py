"""Bridge a loaded PAK into the runtime ``PatyConfig``.

Resolution order (lowest priority first):
    1. Hardware profile defaults (``paty.hardware.profiles``).
    2. Active PAK voice config (``pak.yaml``).
    3. User overrides in ``paty.yaml`` ``pipeline.*`` (always win).

These helpers are pure config transforms; they do not start services.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from paty.config.schema import PatyConfig
from paty.pak.loader import Pak
from paty.pak.registry import PakRegistry
from paty.pak.schema import PakManifest, PakMetadata

DEFAULT_PAK_NAME = "paty"
INLINE_PAK_NAME = "inline"


@dataclass(frozen=True)
class ResolvedPersona:
    """The system prompt and the PAK that produced it.

    ``pak`` is always set: a registered PAK from the user/bundled directory
    or a transient one synthesized from ``config.pak.persona``.
    """

    persona: str
    pak: Pak


def _synthesize_inline_pak(persona: str) -> Pak:
    """Build a transient PAK from inline persona text.

    Voice settings fall through to schema defaults, so ``apply_pak_voice``
    is a no-op here and the hardware profile drives provider/voice — the
    inline path goes through the same pipeline as a registered PAK.
    """
    return Pak(
        manifest=PakManifest(pak=PakMetadata(name=INLINE_PAK_NAME)),
        soul=persona,
        path=Path("<inline>"),
    )


def resolve_persona(
    config: PatyConfig,
    registry: PakRegistry | None = None,
) -> ResolvedPersona:
    """Resolve which persona text to use for this run.

    Priority:
        1. ``config.pak.persona`` — synthesize a transient PAK from the text.
        2. ``config.pak.active`` — explicit PAK pinned in ``paty.yaml``.
        3. ``registry.active_name()`` — pointer set by ``paty pak switch``.
        4. Fall back to the bundled default PAK (``paty``).
    """
    if config.pak.persona is not None:
        pak = _synthesize_inline_pak(config.pak.persona)
        return ResolvedPersona(persona=pak.soul, pak=pak)

    registry = registry or PakRegistry()
    name = config.pak.active or registry.active_name() or DEFAULT_PAK_NAME
    pak = registry.get(name)
    return ResolvedPersona(persona=pak.soul, pak=pak)


def apply_pak_voice(config: PatyConfig, pak: Pak) -> PatyConfig:
    """Return a new ``PatyConfig`` with the PAK's voice settings applied.

    User-provided ``pipeline.tts.voice`` and ``pipeline.llm.model`` win;
    they are treated as explicit overrides.  The PAK's TTS *provider* is
    only adopted alongside the voice — provider without voice would risk
    a silent mismatch with whatever voice the profile defaults to.
    """
    new_tts = config.pipeline.tts
    if pak.manifest.voice.tts.voice and not new_tts.voice:
        new_tts = new_tts.model_copy(
            update={
                "provider": pak.manifest.voice.tts.provider,
                "voice": pak.manifest.voice.tts.voice,
            }
        )

    new_llm = config.pipeline.llm
    if pak.manifest.voice.llm.model and not new_llm.model:
        new_llm = new_llm.model_copy(update={"model": pak.manifest.voice.llm.model})

    new_pipeline = config.pipeline.model_copy(update={"tts": new_tts, "llm": new_llm})
    return config.model_copy(update={"pipeline": new_pipeline})


def warn_if_llm_pin_off_profile(pak: Pak, profile_llm_model: str) -> str | None:
    """Log a loud warning when a PAK pins an LLM other than the profile default.

    Returns the warning string when one was emitted, ``None`` otherwise —
    useful for tests and for echoing the warning to other channels (bus,
    console).
    """
    pin = pak.manifest.voice.llm.model
    if pin and pin != profile_llm_model:
        msg = (
            f"PAK {pak.name!r} pins llm.model={pin!r} but hardware profile "
            f"defaults to {profile_llm_model!r}. Switching to/from this PAK "
            f"will trigger a full LLM reload."
        )
        logger.warning(msg)
        return msg
    return None
