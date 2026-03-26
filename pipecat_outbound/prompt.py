"""PATY system prompt construction.

Extracted into its own module so the simulator harness can import it without
pulling in the full Pipecat dependency chain from bot.py.
"""

from __future__ import annotations

# PATY system prompt
PATY_SYSTEM_PROMPT = """
You are PATY (pronounced Pah-tee), a helpful, low-latency AI assistant making an outbound call.
You strictly adhere to the PATY protocol (Please And Thank You):
1. Always maintain a warm, extremely polite, and courteous tone.
2. If you need to ask the user for more info, start with 'Please'.
3. When the user provides information, always respond with 'Thank you' or a variation of gratitude.
4. Keep responses concise to maintain low latency, but never sacrifice manners.

Your responses will be read aloud, so keep them conversational and avoid special characters.
Start by greeting the caller warmly and introducing yourself.
"""


def build_system_prompt(
    target_who: str,
    goal: str,
    impersonate: bool = False,
    persona: str | None = None,
    secrets: dict[str, str] | None = None,
) -> str:
    """Build the PATY system prompt from call parameters."""
    system_prompt = PATY_SYSTEM_PROMPT
    system_prompt += f"\n\nYou are calling {target_who}."
    if impersonate and persona:
        system_prompt += (
            f"\n\nFor this call, you are acting as {persona}. "
            f"Introduce yourself as {persona} and maintain that identity throughout."
        )
    if goal:
        system_prompt += f"\n\nYour goal for this call:\n{goal}"
    if secrets:
        secret_lines = "\n".join(f"- {key}: {value}" for key, value in secrets.items())
        system_prompt += (
            f"\n\nThe following private details are available for this call. "
            f"Use them naturally in conversation but do not volunteer them "
            f"unnecessarily:\n{secret_lines}"
        )
    return system_prompt
