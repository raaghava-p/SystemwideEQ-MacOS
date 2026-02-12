"""Tests for preset storage: serialization, deserialization, backward compat."""
from __future__ import annotations

import json

import pytest

from equaliser.dsp.filters import EQBand
from equaliser.storage import (
    _serialize_preset,
    _deserialize_preset,
    _sanitize_preset_name,
)


class TestSerializeDeserialize:
    def test_round_trip(self):
        bands = [
            EQBand(1000.0, 6.0, 1.0, filter_type="peaking", enabled=True),
            EQBand(200.0, -3.0, 0.7, filter_type="lowshelf", enabled=False),
        ]
        data = _serialize_preset(bands, -3.0)
        result_bands, gain = _deserialize_preset(data)
        assert gain == pytest.approx(-3.0)
        assert len(result_bands) == 2
        assert result_bands[0].frequency == 1000.0
        assert result_bands[0].filter_type == "peaking"
        assert result_bands[1].filter_type == "lowshelf"
        assert result_bands[1].enabled is False

    def test_backward_compat_missing_filter_type(self):
        """Old presets without filter_type should default to 'peaking'."""
        data = {
            "version": 1,
            "output_gain_db": -3.0,
            "bands": [
                {"frequency": 1000.0, "gain_db": 6.0, "q": 1.0, "enabled": True},
            ],
        }
        bands, gain = _deserialize_preset(data)
        assert bands[0].filter_type == "peaking"

    def test_backward_compat_missing_gain(self):
        data = {"version": 1, "bands": []}
        bands, gain = _deserialize_preset(data)
        assert gain == pytest.approx(-3.0)  # default

    def test_serialization_includes_filter_type(self):
        bands = [EQBand(500.0, 0.0, 1.0, filter_type="highpass")]
        data = _serialize_preset(bands, 0.0)
        assert data["bands"][0]["filter_type"] == "highpass"

    def test_json_round_trip(self):
        """Ensure data survives JSON encode/decode."""
        bands = [EQBand(1000.0, 6.0, 1.0, filter_type="highshelf")]
        data = _serialize_preset(bands, -5.0)
        json_str = json.dumps(data)
        restored = json.loads(json_str)
        result_bands, gain = _deserialize_preset(restored)
        assert result_bands[0].filter_type == "highshelf"
        assert gain == pytest.approx(-5.0)


class TestSanitizePresetName:
    def test_normal_name(self):
        assert _sanitize_preset_name("My Preset") == "My Preset"

    def test_path_traversal_blocked(self):
        name = _sanitize_preset_name("../../etc/passwd")
        assert "/" not in name
        assert ".." not in name

    def test_null_bytes_removed(self):
        name = _sanitize_preset_name("test\x00name")
        assert "\x00" not in name

    def test_empty_after_sanitize_raises(self):
        with pytest.raises(ValueError, match="Invalid preset name"):
            _sanitize_preset_name("...")

    def test_special_chars_removed(self):
        # Path(name).name strips path components first, then regex removes specials
        name = _sanitize_preset_name("test<>name")
        assert name == "testname"

    def test_dangerous_chars_in_filename(self):
        name = _sanitize_preset_name('my|preset?v2')
        assert "|" not in name
        assert "?" not in name
