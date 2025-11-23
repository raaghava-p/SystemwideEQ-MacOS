"""Helpers for visualising the EQ curve."""
from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np

from equaliser.dsp import EQBand, design_peaking_eq


def frequency_response(bands: Iterable[EQBand], sample_rate: float, points: int = 512) -> Tuple[np.ndarray, np.ndarray]:
    freqs = np.logspace(np.log10(20.0), np.log10(sample_rate / 2.0), points)
    w = 2 * np.pi * freqs / sample_rate
    response = np.ones(points, dtype=np.complex128)
    for band in bands:
        b, a = design_peaking_eq(band, sample_rate)
        # Match the runtime filter (a0 normalized to 1)
        b = b / a[0]
        a = a / a[0]
        exp_1 = np.exp(-1j * w)
        exp_2 = np.exp(-2j * w)
        num = b[0] + b[1] * exp_1 + b[2] * exp_2
        den = 1 + a[1] * exp_1 + a[2] * exp_2
        response *= num / den
    magnitude = 20 * np.log10(np.abs(response))
    return freqs, magnitude
