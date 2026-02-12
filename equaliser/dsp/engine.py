"""High-level EQ engine that wraps the filter chain and exposes meters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import numpy as np

from .filters import EQBand, EQFilterChain


@dataclass
class MeterSnapshot:
    """Simple structure for passing meter levels back to the GUI."""

    input_rms: float = 0.0
    output_rms: float = 0.0
    input_peak: float = 0.0
    output_peak: float = 0.0
    spectrum_block: Optional[np.ndarray] = None

    @property
    def input_dbfs(self) -> float:
        return linear_to_db(self.input_rms)

    @property
    def output_dbfs(self) -> float:
        return linear_to_db(self.output_rms)

    @property
    def input_peak_dbfs(self) -> float:
        return linear_to_db(self.input_peak)

    @property
    def output_peak_dbfs(self) -> float:
        return linear_to_db(self.output_peak)


def linear_to_db(value: float, floor: float = -120.0) -> float:
    if value <= 0:
        return floor
    return max(floor, 20 * np.log10(value))


@dataclass
class EQEngine:
    sample_rate: float
    channels: int = 2
    bypass: bool = False
    output_gain_db: float = -3.0  # small headroom
    _chain: EQFilterChain = field(init=False)
    _meter: MeterSnapshot = field(default_factory=MeterSnapshot, init=False)
    _fft_counter: int = field(default=0, init=False)
    _fft_bufs: List[Optional[np.ndarray]] = field(init=False)
    _fft_buf_idx: int = field(default=0, init=False)
    _abs_buf: Optional[np.ndarray] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._chain = EQFilterChain(self.sample_rate, self.channels)
        self._output_gain = 10 ** (self.output_gain_db / 20.0)
        self._fft_bufs: List[Optional[np.ndarray]] = [None, None]

    def preallocate(self, block_size: int) -> None:
        """Pre-allocate RT buffers to avoid allocations in the audio callback."""
        self._fft_bufs = [
            np.empty(block_size, dtype=np.float32),
            np.empty(block_size, dtype=np.float32),
        ]
        self._abs_buf = np.empty((block_size, self.channels), dtype=np.float32)

    def set_bands(self, bands: Iterable[EQBand]) -> None:
        """Update the EQ bands used by the filter chain."""
        self._chain.set_bands(bands)

    def set_output_gain(self, gain_db: float) -> None:
        self.output_gain_db = gain_db
        self._output_gain = 10 ** (gain_db / 20.0)

    def process_block(self, block: np.ndarray) -> np.ndarray:
        if block.ndim != 2 or block.shape[1] != self.channels:
            raise ValueError("Expected audio block shaped (frames, channels)")
        input_level = rms(block)
        # Use pre-allocated abs buffer when available to avoid RT allocations
        if self._abs_buf is not None and self._abs_buf.shape == block.shape:
            np.abs(block, out=self._abs_buf)
            input_peak = float(np.max(self._abs_buf))
        else:
            input_peak = float(np.max(np.abs(block))) if block.size else 0.0
        if self.bypass:
            processed = block.copy()
        else:
            processed = self._chain.process(block)
        # Use non-in-place multiply so `block` stays unmodified for FFT buffer
        processed = processed * self._output_gain
        output_level = rms(processed)
        if self._abs_buf is not None and self._abs_buf.shape == processed.shape:
            np.abs(processed, out=self._abs_buf)
            output_peak = float(np.max(self._abs_buf))
        else:
            output_peak = float(np.max(np.abs(processed))) if processed.size else 0.0
        # Every 4th block, store mono average into double-buffered array (zero allocation)
        spectrum_block = None
        self._fft_counter += 1
        if self._fft_counter >= 4:
            self._fft_counter = 0
            n = block.shape[0]
            buf = self._fft_bufs[self._fft_buf_idx]
            if buf is None or buf.shape[0] != n:
                buf = np.empty(n, dtype=np.float32)
                self._fft_bufs[self._fft_buf_idx] = buf
            np.mean(block, axis=1, out=buf)
            spectrum_block = buf
            self._fft_buf_idx = 1 - self._fft_buf_idx
        self._meter = MeterSnapshot(
            input_level, output_level, input_peak, output_peak,
            spectrum_block,
        )
        processed = np.clip(processed, -1.0, 1.0)
        return processed

    @property
    def meter(self) -> MeterSnapshot:
        return self._meter


def rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block), dtype=np.float64)))
