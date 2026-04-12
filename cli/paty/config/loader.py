"""YAML config loading, env interpolation, and Pydantic validation."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from paty.config.schema import PatyConfig
from paty.utils.env import interpolate_env_recursive


def load_config(path: str | Path) -> PatyConfig:
    """Load a PATY YAML config file and return a validated PatyConfig."""
    yaml = YAML()
    with open(path) as f:
        raw = yaml.load(f)

    if raw is None:
        msg = f"Config file is empty: {path}"
        raise ValueError(msg)

    raw = interpolate_env_recursive(raw)
    return PatyConfig.model_validate(raw)
