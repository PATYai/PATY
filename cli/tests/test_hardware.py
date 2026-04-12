"""Tests for hardware detection with mocked platform info."""

from __future__ import annotations

from unittest.mock import patch

from paty.config.schema import HardwareConfig, HardwareProfile, Platform
from paty.hardware.detect import HardwareInfo, detect_platform
from paty.hardware.profiles import resolve_profile


class TestDetectPlatform:
    def test_arm64_macos_is_mlx(self):
        with (
            patch("paty.hardware.detect.platform.machine", return_value="arm64"),
            patch("paty.hardware.detect.sys.platform", "darwin"),
        ):
            assert detect_platform() == Platform.MLX

    def test_x86_linux_no_cuda_is_cpu(self):
        with (
            patch("paty.hardware.detect.platform.machine", return_value="x86_64"),
            patch("paty.hardware.detect.sys.platform", "linux"),
        ):
            assert detect_platform() == Platform.CPU

    def test_x86_macos_is_cpu(self):
        with (
            patch("paty.hardware.detect.platform.machine", return_value="x86_64"),
            patch("paty.hardware.detect.sys.platform", "darwin"),
        ):
            assert detect_platform() == Platform.CPU


class TestResolveProfile:
    def test_auto_mlx_16gb(self):
        hw = HardwareInfo(platform=Platform.MLX, memory_mb=16_000)
        cfg = HardwareConfig(profile=HardwareProfile.AUTO)
        profile = resolve_profile(cfg, hw)
        assert profile.name == "apple-16gb"

    def test_auto_mlx_24gb(self):
        hw = HardwareInfo(platform=Platform.MLX, memory_mb=24_000)
        cfg = HardwareConfig(profile=HardwareProfile.AUTO)
        profile = resolve_profile(cfg, hw)
        assert profile.name == "apple-24gb"

    def test_auto_cuda(self):
        hw = HardwareInfo(platform=Platform.CUDA, memory_mb=24_000)
        cfg = HardwareConfig(profile=HardwareProfile.AUTO)
        profile = resolve_profile(cfg, hw)
        assert profile.name == "cuda-24gb"

    def test_auto_cpu(self):
        hw = HardwareInfo(platform=Platform.CPU, memory_mb=8_000)
        cfg = HardwareConfig(profile=HardwareProfile.AUTO)
        profile = resolve_profile(cfg, hw)
        assert profile.name == "cpu-only"

    def test_explicit_profile_overrides_auto(self):
        hw = HardwareInfo(platform=Platform.MLX, memory_mb=64_000)
        cfg = HardwareConfig(profile=HardwareProfile.CPU_ONLY)
        profile = resolve_profile(cfg, hw)
        assert profile.name == "cpu-only"
