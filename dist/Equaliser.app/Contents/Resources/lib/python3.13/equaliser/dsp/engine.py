"""High-level EQ engine that wraps the filter chain and exposes meters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

import numpy as np

from .filters import EQBand, EQFilterChain


@dataclass
class MeterSnapshot:
    """Simple structure for passing meter levels back to the GUI."""

    input_rms: float = 0.0
    output_rms: float = 0.0

    @property
    def input_dbfs(self) -> float:
        return linear_to_db(self.input_rms)

    @property
    def output_dbfs(self) -> float:
        return linear_to_db(self.output_rms)


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

    def __post_init__(self) -> None:
        self._chain = EQFilterChain(self.sample_rate, self.channels)
        self._output_gain = 10 ** (self.output_gain_db / 20.0)

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
        if self.bypass:
            processed = block.copy()
        else:
            processed = self._chain.process(block)
        processed *= self._output_gain
        output_level = rms(processed)
        self._meter = MeterSnapshot(input_level, output_level)
        processed = np.clip(processed, -1.0, 1.0)
        return processed

    @property
    def meter(self) -> MeterSnapshot:
        return self._meter


def rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block), dtype=np.float64)))
