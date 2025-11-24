"""py2app entry point for building the Equaliser application bundle."""
from __future__ import annotations

from setuptools import setup

APP = ["equaliser/__main__.py"]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,
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
        "CFBundleVersion": "0.1.0",
        "NSMicrophoneUsageDescription": "Equaliser needs access to the BlackHole driver to capture system audio.",
    },
}

setup(
    name="Equaliser",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
