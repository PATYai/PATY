"""Pipecat observer that extracts audio levels for equalizer visualization."""

from __future__ import annotations

import time

import numpy as np
from pipecat.audio.utils import calculate_audio_volume
from pipecat.frames.frames import (
    InputAudioRawFrame,
    OutputAudioRawFrame,
)
from pipecat.observers.base_observer import BaseObserver, FrameProcessed

from paty.dashboard.snapshot import AudioLevels

# 8 frequency bands for the equalizer (boundaries in Hz at 16kHz sample rate)
_BAND_EDGES = [0, 60, 250, 500, 2000, 4000, 6000, 8000]
_NUM_BANDS = len(_BAND_EDGES)


def _compute_bands(samples: np.ndarray, sample_rate: int) -> list[float]:
    """Compute 8-band frequency magnitudes via FFT."""
    if len(samples) < 16:
        return [0.0] * _NUM_BANDS

    windowed = samples * np.hanning(len(samples))
    fft = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate)

    bands: list[float] = []
    for i in range(len(_BAND_EDGES)):
        lo = _BAND_EDGES[i]
        hi = _BAND_EDGES[i + 1] if i + 1 < len(_BAND_EDGES) else sample_rate // 2
        mask = (freqs >= lo) & (freqs < hi)
        magnitude = float(np.mean(fft[mask])) if np.any(mask) else 0.0
        bands.append(magnitude)

    # Normalize to 0.0-1.0 relative to the max band
    peak = max(bands) if bands else 1.0
    if peak > 0:
        bands = [b / peak for b in bands]
    return bands


class AudioLevelObserver(BaseObserver):
    """Captures audio frames and computes frequency-band levels.

    The shared ``levels`` attribute is updated in-place so any frontend
    can read the latest values without synchronization overhead.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.levels = AudioLevels()

    async def on_process_frame(self, data: FrameProcessed):
        frame = data.frame
        if not isinstance(frame, (InputAudioRawFrame, OutputAudioRawFrame)):
            return

        if not frame.audio:
            return

        try:
            samples = np.frombuffer(frame.audio, dtype=np.int16).astype(np.float32)
            if len(samples) == 0:
                return

            rms = float(calculate_audio_volume(frame.audio, frame.sample_rate))
            bands = _compute_bands(samples, frame.sample_rate)

            self.levels.bands = bands
            self.levels.rms = min(rms, 1.0)
            self.levels.timestamp = time.monotonic()
        except Exception:
            pass
