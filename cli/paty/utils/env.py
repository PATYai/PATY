"""Environment variable interpolation for YAML config values.

Replaces ``${VAR}`` patterns with values from ``os.environ``.
"""

from __future__ import annotations

import os
import re

_ENV_PATTERN = re.compile(r"\$\{([^}]+)}")


def interpolate_env(value: str) -> str:
    """Replace ``${VAR}`` with the corresponding environment variable."""

    def _replace(match: re.Match) -> str:
        var = match.group(1)
        try:
            return os.environ[var]
        except KeyError:
            msg = f"Environment variable {var!r} is not set"
            raise ValueError(msg) from None

    return _ENV_PATTERN.sub(_replace, value)


def interpolate_env_recursive(data: object) -> object:
    """Walk a parsed YAML structure and interpolate env vars in all strings."""
    if isinstance(data, str):
        return interpolate_env(data)
    if isinstance(data, dict):
        return {k: interpolate_env_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [interpolate_env_recursive(item) for item in data]
    return data
