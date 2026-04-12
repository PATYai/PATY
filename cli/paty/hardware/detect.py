"""Hardware detection: platform, GPU, and memory."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass

from paty.config.schema import Platform


@dataclass
class HardwareInfo:
    platform: Platform
    memory_mb: int
    gpu_name: str | None = None


def detect_platform() -> Platform:
    """Detect the compute platform.

    1. arm64 + macOS → MLX
    2. CUDA available → CUDA
    3. Fallback → CPU
    """
    if platform.machine() == "arm64" and sys.platform == "darwin":
        return Platform.MLX

    try:
        import torch

        if torch.cuda.is_available():
            return Platform.CUDA
    except ImportError:
        pass

    return Platform.CPU


def detect_memory_mb() -> int:
    """Detect available memory in MB.

    - macOS: unified memory (total physical)
    - CUDA: GPU VRAM
    - CPU: total system RAM
    """
    if sys.platform == "darwin":
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        return (page_size * page_count) // (1024 * 1024)

    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return props.total_memory // (1024 * 1024)
    except ImportError:
        pass

    try:
        import psutil

        return psutil.virtual_memory().total // (1024 * 1024)
    except ImportError:
        # Last resort: os.sysconf on Linux
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        return (page_size * page_count) // (1024 * 1024)


def _detect_gpu_name() -> str | None:
    """Try to get GPU name, return None if unavailable."""
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return None


def detect_hardware() -> HardwareInfo:
    """Detect platform, memory, and GPU."""
    plat = detect_platform()
    mem = detect_memory_mb()
    gpu = _detect_gpu_name()
    return HardwareInfo(platform=plat, memory_mb=mem, gpu_name=gpu)
