"""Tests for the AutoEQ ParametricEQ.txt parser."""
from __future__ import annotations

import pytest

from equaliser.autoeq import parse_autoeq_text, parse_autoeq_file


SAMPLE_AUTOEQ = """\
Preamp: -6.2 dB
Filter 1: ON PK Fc 31 Hz Gain 4.5 dB Q 1.41
Filter 2: ON PK Fc 62 Hz Gain -2.0 dB Q 1.10
Filter 3: OFF PK Fc 125 Hz Gain 1.0 dB Q 0.71
Filter 4: ON LSC Fc 105 Hz Gain 7.0 dB Q 0.70
Filter 5: ON HSC Fc 10000 Hz Gain -3.5 dB Q 0.71
Filter 6: ON HPQ Fc 30 Hz Gain 0.0 dB Q 0.50
Filter 7: ON LPQ Fc 18000 Hz Gain 0.0 dB Q 0.71
"""


class TestParseAutoEQText:
    def test_preamp(self):
        bands, preamp = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert preamp == pytest.approx(-6.2)

    def test_band_count(self):
        bands, _ = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert len(bands) == 7

    def test_peaking_type(self):
        bands, _ = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert bands[0].filter_type == "peaking"
        assert bands[0].frequency == pytest.approx(31.0)
        assert bands[0].gain_db == pytest.approx(4.5)
        assert bands[0].q == pytest.approx(1.41)
        assert bands[0].enabled is True

    def test_off_filter(self):
        bands, _ = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert bands[2].enabled is False
        assert bands[2].frequency == pytest.approx(125.0)

    def test_lowshelf_type(self):
        bands, _ = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert bands[3].filter_type == "lowshelf"

    def test_highshelf_type(self):
        bands, _ = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert bands[4].filter_type == "highshelf"

    def test_highpass_type(self):
        bands, _ = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert bands[5].filter_type == "highpass"

    def test_lowpass_type(self):
        bands, _ = parse_autoeq_text(SAMPLE_AUTOEQ)
        assert bands[6].filter_type == "lowpass"

    def test_empty_text(self):
        bands, preamp = parse_autoeq_text("")
        assert bands == []
        assert preamp == 0.0

    def test_malformed_lines_skipped(self):
        text = "Preamp: -3.0 dB\nThis is garbage\nFilter 1: ON PK Fc 100 Hz Gain 2.0 dB Q 1.0\n"
        bands, preamp = parse_autoeq_text(text)
        assert preamp == pytest.approx(-3.0)
        assert len(bands) == 1

    def test_no_preamp_defaults_zero(self):
        text = "Filter 1: ON PK Fc 100 Hz Gain 2.0 dB Q 1.0\n"
        bands, preamp = parse_autoeq_text(text)
        assert preamp == 0.0
        assert len(bands) == 1

    def test_alternative_type_aliases(self):
        """LS, HS, HP, LP (without C/Q suffix) should also work."""
        text = """\
Filter 1: ON LS Fc 100 Hz Gain 3.0 dB Q 0.7
Filter 2: ON HS Fc 8000 Hz Gain -2.0 dB Q 0.7
Filter 3: ON HP Fc 30 Hz Gain 0.0 dB Q 0.5
Filter 4: ON LP Fc 16000 Hz Gain 0.0 dB Q 0.7
"""
        bands, _ = parse_autoeq_text(text)
        assert bands[0].filter_type == "lowshelf"
        assert bands[1].filter_type == "highshelf"
        assert bands[2].filter_type == "highpass"
        assert bands[3].filter_type == "lowpass"


class TestParseAutoEQFile:
    def test_reads_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text(SAMPLE_AUTOEQ, encoding="utf-8")
        bands, preamp = parse_autoeq_file(f)
        assert preamp == pytest.approx(-6.2)
        assert len(bands) == 7
