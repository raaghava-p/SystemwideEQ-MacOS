"""Tests for DSP filter design, EQBand, BiquadFilter, and EQFilterChain."""
from __future__ import annotations

import numpy as np
import pytest

from equaliser.dsp.filters import (
    EQBand,
    BiquadFilter,
    EQFilterChain,
    FilterType,
    FILTER_TYPES,
    design_biquad,
    design_peaking_eq,
)

SR = 48000.0


# --- FilterType / FILTER_TYPES -------------------------------------------

class TestFilterType:
    def test_strenum_values(self):
        assert FilterType.PEAKING == "peaking"
        assert FilterType.LOWSHELF == "lowshelf"
        assert FilterType.HIGHSHELF == "highshelf"
        assert FilterType.HIGHPASS == "highpass"
        assert FilterType.LOWPASS == "lowpass"

    def test_filter_types_tuple(self):
        assert isinstance(FILTER_TYPES, tuple)
        assert len(FILTER_TYPES) == 5
        assert "peaking" in FILTER_TYPES


# --- EQBand ---------------------------------------------------------------

class TestEQBand:
    def test_defaults(self):
        band = EQBand(1000.0, 0.0, 1.0)
        assert band.filter_type == "peaking"
        assert band.enabled is True

    def test_invalid_filter_type_clamped(self):
        band = EQBand(1000.0, 0.0, 1.0, filter_type="notreal")
        assert band.filter_type == "peaking"

    def test_valid_filter_types_accepted(self):
        for ft in FILTER_TYPES:
            band = EQBand(1000.0, 0.0, 1.0, filter_type=ft)
            assert band.filter_type == ft

    def test_clip_preserves_filter_type(self):
        band = EQBand(10.0, 3.0, 1.0, filter_type="highshelf")
        clipped = band.clip(20.0, 20000.0)
        assert clipped.frequency == 20.0
        assert clipped.filter_type == "highshelf"
        assert clipped.gain_db == 3.0

    def test_clip_preserves_enabled(self):
        band = EQBand(1000.0, 0.0, 1.0, enabled=False)
        clipped = band.clip(20.0, 20000.0)
        assert clipped.enabled is False


# --- Coefficient design ----------------------------------------------------

class TestDesignBiquad:
    @pytest.mark.parametrize("filter_type", list(FILTER_TYPES))
    def test_all_types_return_valid_coefficients(self, filter_type):
        band = EQBand(1000.0, 6.0, 1.0, filter_type=filter_type)
        b, a = design_biquad(band, SR)
        assert b.shape == (3,)
        assert a.shape == (3,)
        assert b.dtype == np.float64
        assert a.dtype == np.float64
        # a0 should be non-zero (valid biquad)
        assert a[0] != 0.0

    def test_disabled_band_returns_passthrough(self):
        band = EQBand(1000.0, 6.0, 1.0, enabled=False)
        b, a = design_biquad(band, SR)
        np.testing.assert_array_equal(b, [1.0, 0.0, 0.0])
        np.testing.assert_array_equal(a, [1.0, 0.0, 0.0])

    def test_peaking_zero_gain_is_near_unity(self):
        band = EQBand(1000.0, 0.0, 1.0, filter_type="peaking")
        b, a = design_biquad(band, SR)
        # With 0 dB gain, b ≈ a (unity filter)
        np.testing.assert_allclose(b, a, atol=1e-10)

    def test_design_peaking_eq_backward_compat(self):
        band = EQBand(1000.0, 6.0, 1.0)
        b1, a1 = design_peaking_eq(band, SR)
        b2, a2 = design_biquad(band, SR)
        np.testing.assert_array_equal(b1, b2)
        np.testing.assert_array_equal(a1, a2)

    def test_unknown_filter_type_falls_back_to_peaking(self):
        """design_biquad uses _DESIGNERS.get(..., design_peaking_eq)."""
        band = EQBand(1000.0, 6.0, 1.0)
        # __post_init__ clamps to peaking, so manually override to test fallback
        object.__setattr__(band, "filter_type", "bogus")
        b, a = design_biquad(band, SR)
        # Should still produce valid coefficients (peaking fallback)
        assert b.shape == (3,)
        assert a.shape == (3,)


# --- BiquadFilter ----------------------------------------------------------

class TestBiquadFilter:
    def test_from_eq_band(self):
        band = EQBand(1000.0, 6.0, 1.0)
        filt = BiquadFilter.from_eq_band(band, SR)
        assert filt.channels == 2

    def test_process_shape(self):
        band = EQBand(1000.0, 6.0, 1.0)
        filt = BiquadFilter.from_eq_band(band, SR, channels=2)
        block = np.random.randn(256, 2).astype(np.float32)
        out = filt.process(block)
        assert out.shape == block.shape

    def test_passthrough_preserves_signal(self):
        band = EQBand(1000.0, 0.0, 1.0, enabled=False)
        filt = BiquadFilter.from_eq_band(band, SR, channels=2)
        block = np.random.randn(256, 2).astype(np.float32)
        out = filt.process(block)
        np.testing.assert_allclose(out, block, atol=1e-6)

    def test_invalid_block_ndim_raises(self):
        band = EQBand(1000.0, 6.0, 1.0)
        filt = BiquadFilter.from_eq_band(band, SR)
        with pytest.raises(ValueError, match="2-D"):
            filt.process(np.zeros(100, dtype=np.float32))

    def test_channel_mismatch_raises(self):
        band = EQBand(1000.0, 6.0, 1.0)
        filt = BiquadFilter.from_eq_band(band, SR, channels=2)
        with pytest.raises(ValueError, match="channel mismatch"):
            filt.process(np.zeros((100, 1), dtype=np.float32))


# --- EQFilterChain ---------------------------------------------------------

class TestEQFilterChain:
    def test_empty_chain_passthrough(self):
        chain = EQFilterChain(SR)
        block = np.random.randn(256, 2).astype(np.float32)
        out = chain.process(block)
        # No bands set — should return the same block object
        assert out is block

    def test_set_bands_skips_disabled(self):
        chain = EQFilterChain(SR)
        chain.set_bands([
            EQBand(1000.0, 6.0, 1.0, enabled=True),
            EQBand(2000.0, 3.0, 1.0, enabled=False),
        ])
        assert len(chain._filters) == 1

    def test_process_applies_gain(self):
        """A +6 dB peaking band at 1 kHz should boost a 1 kHz sine."""
        chain = EQFilterChain(SR)
        chain.set_bands([EQBand(1000.0, 6.0, 1.0)])
        t = np.arange(1024) / SR
        sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
        block = np.column_stack([sine, sine])
        out = chain.process(block)
        # Output RMS should be larger than input RMS
        assert np.sqrt(np.mean(out ** 2)) > np.sqrt(np.mean(block ** 2))
