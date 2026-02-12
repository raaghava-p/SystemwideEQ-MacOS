"""py2app build script for the Equaliser macOS app bundle.

Usage:
    python scripts/build_app.py py2app
"""
from __future__ import annotations

from setuptools import setup

from equaliser import __version__

APP = ["equaliser/__main__.py"]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "equaliser/resources/equaliser.icns",
    "includes": [
        "matplotlib.backends.backend_qtagg",
        "numpy",
        "sounddevice",
    ],
    "packages": ["equaliser", "_sounddevice_data"],
    "compressed": False,
    "plist": {
        "CFBundleName": "Equaliser",
        "CFBundleDisplayName": "Equaliser",
        "CFBundleIdentifier": "com.equaliser.app",
        "CFBundleVersion": __version__,
        "NSMicrophoneUsageDescription": "Equaliser needs access to the BlackHole driver to capture system audio.",
    },
}

setup(
    name="Equaliser",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
