"""Parser for AutoEQ ParametricEQ.txt headphone profiles."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from equaliser.dsp.filters import EQBand

_TYPE_MAP = {
    "PK": "peaking",
    "LSC": "lowshelf",
    "LS": "lowshelf",
    "HSC": "highshelf",
    "HS": "highshelf",
    "HPQ": "highpass",
    "HP": "highpass",
    "LPQ": "lowpass",
    "LP": "lowpass",
}

_PREAMP_RE = re.compile(r"Preamp:\s*(-?[\d.]+)\s*dB", re.IGNORECASE)
_FILTER_RE = re.compile(
    r"Filter\s+\d+:\s*(?P<state>ON|OFF)\s+(?P<type>\w+)\s+"
    r"Fc\s+(?P<freq>[\d.]+)\s*Hz\s+"
    r"Gain\s+(?P<gain>-?[\d.]+)\s*dB\s+"
    r"Q\s+(?P<q>[\d.]+)",
    re.IGNORECASE,
)


def parse_autoeq_text(text: str) -> Tuple[List[EQBand], float]:
    """Parse AutoEQ ParametricEQ.txt content.

    Returns (bands, preamp_db).
    """
    preamp_db = 0.0
    bands: List[EQBand] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m = _PREAMP_RE.search(line)
        if m:
            preamp_db = float(m.group(1))
            continue

        m = _FILTER_RE.search(line)
        if m:
            enabled = m.group("state").upper() == "ON"
            filter_type = _TYPE_MAP.get(m.group("type").upper(), "peaking")
            freq = float(m.group("freq"))
            gain = float(m.group("gain"))
            q = float(m.group("q"))
            bands.append(EQBand(
                frequency=freq,
                gain_db=gain,
                q=q,
                filter_type=filter_type,
                enabled=enabled,
            ))

    return bands, preamp_db


def parse_autoeq_file(filepath: str | Path) -> Tuple[List[EQBand], float]:
    """Read and parse an AutoEQ ParametricEQ.txt file."""
    text = Path(filepath).read_text(encoding="utf-8")
    return parse_autoeq_text(text)
