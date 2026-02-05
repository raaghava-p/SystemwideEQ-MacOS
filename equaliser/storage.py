"""Persistence layer for EQ presets and session state."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple

from equaliser.dsp.filters import EQBand

STORAGE_VERSION = 1
APP_NAME = "Equaliser"


def _sanitize_preset_name(name: str) -> str:
    """Sanitize preset name to prevent path traversal and invalid filenames.

    Removes path separators, null bytes, and other dangerous characters.
    Returns a safe filename component.
    """
    # Remove any path components (prevent traversal)
    name = Path(name).name
    # Remove null bytes and other control characters
    name = re.sub(r'[\x00-\x1f\x7f]', '', name)
    # Remove characters that are problematic in filenames
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Remove leading/trailing dots and spaces
    name = name.strip('. ')
    # Ensure we have something left
    if not name:
        raise ValueError("Invalid preset name")
    return name


def get_app_data_dir() -> Path:
    """Return the app data directory, creating it if necessary."""
    data_dir = Path.home() / "Library" / "Application Support" / APP_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_presets_dir() -> Path:
    """Return the presets directory, creating it if necessary."""
    presets_dir = get_app_data_dir() / "presets"
    presets_dir.mkdir(parents=True, exist_ok=True)
    return presets_dir


def _serialize_preset(bands: List[EQBand], output_gain_db: float) -> dict:
    """Convert bands and gain to a serializable dict."""
    return {
        "version": STORAGE_VERSION,
        "output_gain_db": output_gain_db,
        "bands": [asdict(band) for band in bands],
    }


def _deserialize_preset(data: dict) -> Tuple[List[EQBand], float]:
    """Convert stored dict back to bands and gain."""
    bands = [EQBand(**band_data) for band_data in data.get("bands", [])]
    output_gain_db = data.get("output_gain_db", -3.0)
    return bands, output_gain_db


def save_session(bands: List[EQBand], output_gain_db: float) -> None:
    """Save current session state to disk."""
    session_file = get_app_data_dir() / "session.json"
    data = _serialize_preset(bands, output_gain_db)
    session_file.write_text(json.dumps(data, indent=2))


def load_session() -> Optional[Tuple[List[EQBand], float]]:
    """Load session state from disk. Returns None if no session exists."""
    session_file = get_app_data_dir() / "session.json"
    if not session_file.exists():
        return None
    try:
        data = json.loads(session_file.read_text())
        return _deserialize_preset(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def save_preset(name: str, bands: List[EQBand], output_gain_db: float) -> None:
    """Save a named preset."""
    safe_name = _sanitize_preset_name(name)
    preset_file = get_presets_dir() / f"{safe_name}.json"
    data = _serialize_preset(bands, output_gain_db)
    preset_file.write_text(json.dumps(data, indent=2))


def load_preset(name: str) -> Optional[Tuple[List[EQBand], float]]:
    """Load a named preset. Returns None if not found."""
    try:
        safe_name = _sanitize_preset_name(name)
    except ValueError:
        return None
    preset_file = get_presets_dir() / f"{safe_name}.json"
    if not preset_file.exists():
        return None
    try:
        data = json.loads(preset_file.read_text())
        return _deserialize_preset(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def list_presets() -> List[str]:
    """Return a list of all saved preset names."""
    presets_dir = get_presets_dir()
    return sorted([p.stem for p in presets_dir.glob("*.json")])


def delete_preset(name: str) -> bool:
    """Delete a preset. Returns True if deleted, False if not found."""
    try:
        safe_name = _sanitize_preset_name(name)
    except ValueError:
        return False
    preset_file = get_presets_dir() / f"{safe_name}.json"
    if preset_file.exists():
        preset_file.unlink()
        return True
    return False
