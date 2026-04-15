"""GUI-agnostic dashboard data layer for pipeline metrics and audio levels."""

from __future__ import annotations

from paty.dashboard.collectors import RollingCollector
from paty.dashboard.provider import DashboardProvider
from paty.dashboard.snapshot import AudioLevels, DashboardSnapshot, StageMetrics

__all__ = [
    "AudioLevels",
    "DashboardProvider",
    "DashboardSnapshot",
    "RollingCollector",
    "StageMetrics",
]
