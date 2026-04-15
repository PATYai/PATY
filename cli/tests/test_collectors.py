"""Tests for the RollingCollector percentile and statistics computation."""

from __future__ import annotations

import pytest

from paty.dashboard.collectors import RollingCollector


def test_empty_collector_returns_none():
    c = RollingCollector()
    assert c.avg("missing") is None
    assert c.percentile("missing", 95) is None
    assert c.max_val("missing") is None
    assert c.count("missing") == 0


def test_single_value():
    c = RollingCollector()
    c.record("m", 0.5)
    assert c.avg("m") == 0.5
    assert c.percentile("m", 50) == 0.5
    assert c.max_val("m") == 0.5
    assert c.count("m") == 1


def test_avg_and_max():
    c = RollingCollector()
    for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
        c.record("m", v)
    assert c.avg("m") == pytest.approx(3.0)
    assert c.max_val("m") == 5.0
    assert c.count("m") == 5


def test_percentile_p50():
    c = RollingCollector()
    for v in range(1, 101):
        c.record("m", float(v))
    p50 = c.percentile("m", 50)
    assert p50 == pytest.approx(50.5, abs=0.5)


def test_percentile_p95():
    c = RollingCollector()
    for v in range(1, 101):
        c.record("m", float(v))
    p95 = c.percentile("m", 95)
    assert p95 == pytest.approx(95.05, abs=0.5)


def test_window_size_evicts_old_values():
    c = RollingCollector(window_size=5)
    for v in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]:
        c.record("m", v)
    # Only last 5 values should remain: 30, 40, 50, 60, 70
    assert c.count("m") == 5
    assert c.avg("m") == pytest.approx(50.0)
    assert c.max_val("m") == 70.0


def test_multiple_metrics_independent():
    c = RollingCollector()
    c.record("a", 1.0)
    c.record("b", 100.0)
    assert c.avg("a") == 1.0
    assert c.avg("b") == 100.0
    assert c.count("a") == 1
    assert c.count("b") == 1
