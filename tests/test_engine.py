"""Tests for the EQ engine: metering, peak detection, spectrum, preallocation."""
from __future__ import annotations

import numpy as np
import pytest

from equaliser.dsp.engine import EQEngine, MeterSnapshot, linear_to_db, rms
from equaliser.dsp.filters import EQBand


SR = 48000.0
BLOCK = 256
CHANNELS = 2


def _make_engine() -> EQEngine:
    engine = EQEngine(sample_rate=SR, channels=CHANNELS)
    engine.preallocate(BLOCK)
    return engine


def _silence(frames: int = BLOCK) -> np.ndarray:
    return np.zeros((frames, CHANNELS), dtype=np.float32)


def _sine_block(freq: float = 1000.0, frames: int = BLOCK) -> np.ndarray:
    t = np.arange(frames) / SR
    s = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.column_stack([s, s])


# --- Utility functions -----------------------------------------------------

class TestUtilities:
    def test_linear_to_db_positive(self):
        assert linear_to_db(1.0) == pytest.approx(0.0)

    def test_linear_to_db_zero(self):
        assert linear_to_db(0.0) == -120.0

    def test_linear_to_db_negative(self):
        assert linear_to_db(-1.0) == -120.0

    def test_rms_silence(self):
        assert rms(_silence()) == 0.0

    def test_rms_signal(self):
        block = _sine_block()
        assert rms(block) > 0.0

    def test_rms_empty(self):
        assert rms(np.empty((0, 2), dtype=np.float32)) == 0.0


# --- MeterSnapshot ---------------------------------------------------------

class TestMeterSnapshot:
    def test_defaults(self):
        m = MeterSnapshot()
        assert m.input_rms == 0.0
        assert m.output_rms == 0.0
        assert m.input_peak == 0.0
        assert m.output_peak == 0.0
        assert m.spectrum_block is None

    def test_dbfs_properties(self):
        m = MeterSnapshot(input_rms=1.0, output_rms=0.5)
        assert m.input_dbfs == pytest.approx(0.0)
        assert m.output_dbfs == pytest.approx(-6.02, abs=0.1)

    def test_peak_dbfs_properties(self):
        m = MeterSnapshot(input_peak=1.0, output_peak=0.25)
        assert m.input_peak_dbfs == pytest.approx(0.0)
        assert m.output_peak_dbfs == pytest.approx(-12.04, abs=0.1)


# --- EQEngine --------------------------------------------------------------

class TestEQEngine:
    def test_process_block_shape(self):
        engine = _make_engine()
        block = _sine_block()
        out = engine.process_block(block)
        assert out.shape == block.shape

    def test_process_block_invalid_shape_raises(self):
        engine = _make_engine()
        with pytest.raises(ValueError, match="Expected audio block"):
            engine.process_block(np.zeros(100, dtype=np.float32))

    def test_metering_updates(self):
        engine = _make_engine()
        engine.process_block(_sine_block())
        m = engine.meter
        assert m.input_rms > 0.0
        assert m.output_rms > 0.0
        assert m.input_peak > 0.0

    def test_silence_metering(self):
        engine = _make_engine()
        engine.process_block(_silence())
        m = engine.meter
        assert m.input_rms == 0.0
        assert m.input_peak == 0.0

    def test_bypass_passes_signal_through(self):
        engine = _make_engine()
        engine.set_bands([EQBand(1000.0, 12.0, 1.0)])
        engine.bypass = True
        block = _sine_block()
        out = engine.process_block(block)
        # Output should be block * output_gain, not EQ-processed
        expected_gain = 10 ** (engine.output_gain_db / 20.0)
        np.testing.assert_allclose(
            np.clip(block * expected_gain, -1, 1), out, atol=1e-5
        )

    def test_output_gain(self):
        engine = _make_engine()
        engine.set_output_gain(-6.0)
        block = _sine_block()
        out = engine.process_block(block)
        # Output should be attenuated
        assert np.max(np.abs(out)) < np.max(np.abs(block))

    def test_clipping(self):
        engine = _make_engine()
        engine.set_output_gain(20.0)
        block = _sine_block()
        out = engine.process_block(block)
        assert np.max(out) <= 1.0
        assert np.min(out) >= -1.0


# --- Spectrum block --------------------------------------------------------

class TestSpectrumBlock:
    def test_spectrum_appears_every_4th_block(self):
        engine = _make_engine()
        spectrum_blocks = []
        for i in range(8):
            engine.process_block(_sine_block())
            spectrum_blocks.append(engine.meter.spectrum_block)
        # Blocks 3 and 7 (0-indexed: counter hits 4 at these)
        non_none = [i for i, s in enumerate(spectrum_blocks) if s is not None]
        assert len(non_none) == 2

    def test_spectrum_block_shape(self):
        engine = _make_engine()
        for _ in range(4):
            engine.process_block(_sine_block())
        spec = engine.meter.spectrum_block
        assert spec is not None
        assert spec.shape == (BLOCK,)
        assert spec.dtype == np.float32

    def test_spectrum_block_is_mono_average(self):
        engine = _make_engine()
        block = _sine_block()
        for _ in range(4):
            engine.process_block(block)
        spec = engine.meter.spectrum_block
        expected = np.mean(block, axis=1)
        np.testing.assert_allclose(spec, expected, atol=1e-6)


# --- Preallocation ---------------------------------------------------------

class TestPreallocation:
    def test_preallocate_creates_buffers(self):
        engine = EQEngine(sample_rate=SR, channels=CHANNELS)
        engine.preallocate(BLOCK)
        assert engine._fft_bufs[0] is not None
        assert engine._fft_bufs[1] is not None
        assert engine._fft_bufs[0].shape == (BLOCK,)
        assert engine._abs_buf is not None
        assert engine._abs_buf.shape == (BLOCK, CHANNELS)

    def test_engine_without_prealloc_still_works(self):
        engine = EQEngine(sample_rate=SR, channels=CHANNELS)
        # No preallocate call — should still work via fallback paths
        out = engine.process_block(_sine_block())
        assert out.shape == (BLOCK, CHANNELS)

    def test_preallocated_abs_buf_used_for_peaks(self):
        engine = _make_engine()
        block = _sine_block()
        engine.process_block(block)
        # After processing, abs_buf should have been written to
        assert engine._abs_buf is not None
