"""Synthetic signals used for testing the DSP pipeline."""
from __future__ import annotations

import numpy as np


def sine_wave(freq: float, sample_rate: float, duration: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(int(sample_rate * duration)) / sample_rate
    wave = amplitude * np.sin(2 * np.pi * freq * t)
    return np.stack([wave, wave], axis=1)


def white_noise(sample_rate: float, duration: float, amplitude: float = 0.2) -> np.ndarray:
    samples = amplitude * np.random.uniform(-1.0, 1.0, int(sample_rate * duration))
    return np.stack([samples, samples], axis=1)


def sweep(start_freq: float, end_freq: float, sample_rate: float, duration: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    phase = 2 * np.pi * (start_freq * t + (end_freq - start_freq) * t**2 / (2 * duration))
    signal = amplitude * np.sin(phase)
    return np.stack([signal, signal], axis=1)
