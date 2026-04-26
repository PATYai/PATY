"""Bridge a loaded PAK into the runtime ``PatyConfig``.

Resolution order (lowest priority first):
    1. Hardware profile defaults (``paty.hardware.profiles``).
    2. Active PAK voice config (``pak.yaml``).
    3. User overrides in ``paty.yaml`` ``pipeline.*`` (always win).

These helpers are pure config transforms; they do not start services.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from paty.config.schema import PatyConfig
from paty.pak.loader import Pak
from paty.pak.registry import PakRegistry

DEFAULT_PAK_NAME = "paty"


@dataclass(frozen=True)
class ResolvedPersona:
    """The system prompt and (optional) PAK that produced it.

    ``pak`` is ``None`` only on the legacy ``agent.persona`` path — useful
    for callers that want to behave differently when no PAK is in play
    (e.g. skip conversation namespacing).
    """

    persona: str
    pak: Pak | None


def resolve_persona(
    config: PatyConfig,
    registry: PakRegistry | None = None,
) -> ResolvedPersona:
    """Resolve which persona text to use for this run.

    Priority:
        1. ``config.agent.persona`` (legacy inline) — returns ``pak=None``.
        2. ``config.pak.active`` — load that PAK from the registry.
        3. Fall back to the bundled default PAK.
    """
    if config.agent is not None:
        return ResolvedPersona(persona=config.agent.persona, pak=None)

    registry = registry or PakRegistry()
    name = config.pak.active or DEFAULT_PAK_NAME
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
