"""Tests for the PATY metrics observer and setup."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from paty.config.schema import MetricsConfig
from paty.metrics.observer import PipelineMetricsObserver, _classify_processor


class TestClassifyProcessor:
    def test_stt_keywords(self):
        assert _classify_processor("AssemblyAISTTService") == "stt"
        assert _classify_processor("WhisperSTT") == "stt"

    def test_llm_keywords(self):
        assert _classify_processor("OpenAILLMService") == "llm"
        assert _classify_processor("OllamaLLM") == "llm"

    def test_tts_keywords(self):
        assert _classify_processor("CartesiaTTSService") == "tts"
        assert _classify_processor("MLXAudioTTSService") == "tts"
        assert _classify_processor("KokoroTTS") == "tts"

    def test_unknown(self):
        assert _classify_processor("SomeRandomProcessor") == "unknown"


class TestPipelineMetricsObserver:
    def setup_method(self):
        self._reader = InMemoryMetricReader()
        self._provider = MeterProvider(metric_readers=[self._reader])
        self._meter = self._provider.get_meter("paty-test")

    def teardown_method(self):
        self._provider.shutdown()

    def test_observer_creates_instruments(self):
        observer = PipelineMetricsObserver(meter=self._meter)
        assert observer._ttfb is not None
        assert observer._processing is not None
        assert observer._llm_tokens is not None
        assert observer._tts_chars is not None

    @pytest.mark.asyncio
    async def test_ttfb_recording(self):
        from pipecat.frames.frames import MetricsFrame
        from pipecat.metrics.metrics import TTFBMetricsData

        observer = PipelineMetricsObserver(meter=self._meter)

        ttfb_data = TTFBMetricsData(
            processor="OpenAILLMService", model="gpt-4", value=0.35
        )
        frame = MetricsFrame(data=[ttfb_data])
        pushed = MagicMock()
        pushed.frame = frame

        await observer.on_push_frame(pushed)

        # Force collection
        data = self._reader.get_metrics_data()
        metric_names = []
        for rm in data.resource_metrics:
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    metric_names.append(m.name)

        assert "paty_llm_ttfb_seconds" in metric_names

    @pytest.mark.asyncio
    async def test_tts_chars_recording(self):
        from pipecat.frames.frames import MetricsFrame
        from pipecat.metrics.metrics import TTSUsageMetricsData

        observer = PipelineMetricsObserver(meter=self._meter)

        tts_data = TTSUsageMetricsData(processor="KokoroTTS", value=42)
        frame = MetricsFrame(data=[tts_data])
        pushed = MagicMock()
        pushed.frame = frame

        await observer.on_push_frame(pushed)

        data = self._reader.get_metrics_data()
        metric_names = []
        for rm in data.resource_metrics:
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    metric_names.append(m.name)

        assert "paty_tts_characters_total" in metric_names


class TestSetupMetrics:
    def test_setup_returns_handle(self):
        from paty.metrics.setup import setup_metrics

        config = MetricsConfig(enabled=True, console_interval=0, prometheus=False)
        handle = setup_metrics(config)
        assert handle.meter is not None
        assert handle.observer is not None
        assert handle.in_memory_reader is not None

    def test_disabled_still_returns_handle(self):
        from paty.metrics.setup import setup_metrics

        config = MetricsConfig(enabled=False, console_interval=0, prometheus=False)
        handle = setup_metrics(config)
        assert handle.observer is not None
