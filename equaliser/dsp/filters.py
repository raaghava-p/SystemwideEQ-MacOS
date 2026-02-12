"""DSP helpers for parametric EQ filters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import numpy as np


@dataclass
class EQBand:
    """Describes a single parametric peaking filter band."""

    frequency: float  # Hz
    gain_db: float  # dB boost/cut
    q: float  # quality factor
    enabled: bool = True

    def clip(self, min_freq: float, max_freq: float) -> "EQBand":
        """Return a copy with frequency constrained to a safe range."""
        freq = float(np.clip(self.frequency, min_freq, max_freq))
        return EQBand(freq, self.gain_db, self.q, self.enabled)


def design_peaking_eq(band: EQBand, sample_rate: float) -> np.ndarray:
    """Return normalized RBJ coefficients for a peaking EQ."""
    if not band.enabled:
        b = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        a = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        return b, a

    freq = np.clip(band.frequency, 20.0, sample_rate / 2.1)
    gain = band.gain_db
    q = max(0.05, band.q)
    a_gain = 10 ** (gain / 40.0)
    omega = 2 * np.pi * freq / sample_rate
    alpha = np.sin(omega) / (2 * q)

    b0 = 1 + alpha * a_gain
    b1 = -2 * np.cos(omega)
    b2 = 1 - alpha * a_gain
    a0 = 1 + alpha / a_gain
    a1 = -2 * np.cos(omega)
    a2 = 1 - alpha / a_gain

    return (
        np.array([b0, b1, b2], dtype=np.float64),
        np.array([a0, a1, a2], dtype=np.float64),
    )


class BiquadFilter:
    """RBJ biquad implementation for stereo (or multi-channel) audio."""

    def __init__(self, b: np.ndarray, a: np.ndarray, channels: int = 2):
        if channels < 1:
            raise ValueError("BiquadFilter needs at least one channel")
        if b.shape != (3,) or a.shape != (3,):
            raise ValueError("BiquadFilter expects (3,) coefficient arrays")
        # Normalize so a0 == 1
        b = b / a[0]
        a = a / a[0]
        self.b0, self.b1, self.b2 = b
        self.a1, self.a2 = a[1], a[2]
        self.channels = channels
        self.state = np.zeros((channels, 2), dtype=np.float32)

    @staticmethod
    def from_eq_band(band: EQBand, sample_rate: float, channels: int = 2) -> "BiquadFilter":
        """Create a peaking EQ filter from an EQBand definition."""
        b, a = design_peaking_eq(band, sample_rate)
        return BiquadFilter(b, a, channels)

    def process(self, block: np.ndarray) -> np.ndarray:
        """Process an audio block of shape (frames, channels)."""
        if block.ndim != 2:
            raise ValueError("Audio block must be 2-D (frames, channels)")
        if block.shape[1] != self.channels:
            raise ValueError("Audio block channel mismatch")

        y = np.empty_like(block)
        for ch in range(self.channels):
            x = block[:, ch]
            y_ch = y[:, ch]
            z1, z2 = self.state[ch]
            b0, b1, b2 = self.b0, self.b1, self.b2
            a1, a2 = self.a1, self.a2
            for i, sample in enumerate(x):
                out = b0 * sample + z1
                z1_new = b1 * sample - a1 * out + z2
                z2 = b2 * sample - a2 * out
                z1 = z1_new
                y_ch[i] = out
            self.state[ch, 0] = z1
            self.state[ch, 1] = z2
        return y


class EQFilterChain:
    """Maintains a list of biquad filters for an EQ preset."""

    def __init__(self, sample_rate: float, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self._bands: List[EQBand] = []
        self._filters: List[BiquadFilter] = []

    @property
    def bands(self) -> List[EQBand]:
        return list(self._bands)

    def set_bands(self, bands: Iterable[EQBand]) -> None:
        self._bands = [b.clip(20.0, self.sample_rate / 2.1) for b in bands]
        self._filters = [BiquadFilter.from_eq_band(b, self.sample_rate, self.channels) for b in self._bands if b.enabled]

    def process(self, block: np.ndarray) -> np.ndarray:
        if not self._filters:
            return block
        output = block
        for filt in self._filters:
            output = filt.process(output)
        return output
